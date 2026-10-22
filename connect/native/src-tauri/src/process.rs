use crate::policy::parse_handshake;
use std::{
    io::{BufRead, BufReader, Read, Write},
    path::Path,
    process::{Child, Command, Stdio},
    sync::mpsc,
    time::{Duration, Instant},
};
use url::Url;

pub struct ManagedChild {
    child: Child,
    stopped: bool,
    #[cfg(windows)]
    _job: std::os::windows::io::OwnedHandle,
}

impl ManagedChild {
    pub fn launch(
        binary: &Path,
        runtime: &Path,
        full: bool,
    ) -> Result<(Self, mpsc::Receiver<Result<Url, &'static str>>), &'static str> {
        let mut command = Command::new(binary);
        command
            .args(["--port", "0"])
            .arg("--runtime-dir")
            .arg(runtime);
        if full {
            command.arg("--full");
        }
        let (child, lines) = Self::spawn(command)?;
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let result = lines
                .recv()
                .unwrap_or(Err("bridge_handshake_failed"))
                .and_then(|line| parse_handshake(&line));
            let _ = tx.send(result);
        });
        Ok((child, rx))
    }

    pub fn login(
        binary: &Path,
    ) -> Result<(Self, mpsc::Receiver<Result<String, &'static str>>), &'static str> {
        let mut command = Command::new(binary);
        command.arg("--login");
        Self::spawn(command)
    }

    fn spawn(
        mut command: Command,
    ) -> Result<(Self, mpsc::Receiver<Result<String, &'static str>>), &'static str> {
        // Create the named Job before the onefile bootloader starts. The Python
        // worker explicitly joins it before doing any work, closing the race
        // where a bootloader child predates AssignProcessToJobObject below.
        #[cfg(windows)]
        let (job, job_name) = windows_job()?;
        #[cfg(windows)]
        command.arg("--job-name").arg(job_name);
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        for name in [
            "PYTHONPATH",
            "PYTHONHOME",
            "NODE_OPTIONS",
            "MDTERO_CONNECT_APP_DIR",
        ] {
            command.env_remove(name);
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000 | 0x00000200); // no console, new group
        }
        let mut child = command.spawn().map_err(|_| "bridge_spawn_failed")?;
        #[cfg(windows)]
        {
            use std::os::windows::io::AsRawHandle;
            let assigned = unsafe {
                windows_sys::Win32::System::JobObjects::AssignProcessToJobObject(
                    job.as_raw_handle(),
                    child.as_raw_handle(),
                )
            };
            if assigned == 0 {
                let _ = child.kill();
                let _ = child.wait();
                return Err("bridge_job_failed");
            }
        }
        let stdout = child.stdout.take().ok_or("bridge_stdout_missing")?;
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let mut line = String::new();
            let result = BufReader::new(stdout)
                .take(8192)
                .read_line(&mut line)
                .map_err(|_| "bridge_handshake_failed")
                .map(|_| line);
            let _ = tx.send(result);
            // stdout is deliberately not forwarded into the web page or logs.
        });
        Ok((
            Self {
                child,
                stopped: false,
                #[cfg(windows)]
                _job: job,
            },
            rx,
        ))
    }

    pub fn pid(&self) -> u32 {
        self.child.id()
    }

    pub fn shutdown(&mut self) {
        if self.stopped {
            return;
        }
        self.stopped = true;
        if let Some(mut input) = self.child.stdin.take() {
            let _ = input.write_all(b"shutdown\n");
        }
        let deadline = Instant::now() + Duration::from_secs(4);
        while Instant::now() < deadline {
            match self.child.try_wait() {
                Ok(Some(_)) | Err(_) => break,
                Ok(None) => std::thread::sleep(Duration::from_millis(30)),
            }
        }
        #[cfg(unix)]
        unsafe {
            libc::kill(-(self.child.id() as i32), libc::SIGKILL);
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
        // Windows' owned Job handle is closed on drop, killing remaining descendants.
    }
}

impl Drop for ManagedChild {
    fn drop(&mut self) {
        self.shutdown();
    }
}

#[cfg(windows)]
fn windows_job() -> Result<(std::os::windows::io::OwnedHandle, String), &'static str> {
    use std::os::windows::io::{FromRawHandle, OwnedHandle};
    use windows_sys::Win32::System::JobObjects::*;
    let name = format!("Local\\MdteroConnect-{}", uuid::Uuid::new_v4());
    let wide: Vec<u16> = name.encode_utf16().chain(Some(0)).collect();
    unsafe {
        let raw = CreateJobObjectW(std::ptr::null(), wide.as_ptr());
        if raw.is_null() {
            return Err("bridge_job_failed");
        }
        let owned = OwnedHandle::from_raw_handle(raw);
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if SetInformationJobObject(
            raw,
            JobObjectExtendedLimitInformation,
            &limits as *const _ as _,
            std::mem::size_of_val(&limits) as u32,
        ) == 0
        {
            return Err("bridge_job_failed");
        }
        Ok((owned, name))
    }
}
