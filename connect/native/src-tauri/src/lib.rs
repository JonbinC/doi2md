mod policy;
mod process;

use policy::{allow_navigation, safe_filename, same_bridge};
use process::ManagedChild;
use std::{
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Mutex,
    },
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tauri::{
    webview::{DownloadEvent, NewWindowResponse, PageLoadEvent},
    Manager, WebviewUrl, WebviewWindowBuilder,
};
use url::Url;

struct NativeState {
    bridge: Mutex<Option<ManagedChild>>,
    login: Mutex<Option<ManagedChild>>,
    origin: Mutex<Option<Url>>,
    binary: PathBuf,
    runtime: PathBuf,
    full: bool,
    exiting: AtomicBool,
    generation: AtomicU64,
    login_generation: AtomicU64,
    smoke_download: Mutex<Option<PathBuf>>,
}

const SMOKE_EXPORT: &str = "@misc{mdtero_native_smoke, title={Synthetic native download test}}\n";

fn resources(
    app: &tauri::AppHandle,
) -> Result<(PathBuf, PathBuf, bool), Box<dyn std::error::Error>> {
    let suffix = std::env::consts::EXE_SUFFIX;
    let mut binary = std::env::current_exe()?
        .parent()
        .ok_or("missing executable directory")?
        .join(format!("mdtero-connect-bridge{suffix}"));
    let mut runtime = app.path().resource_dir()?.join("runtime");
    #[cfg(debug_assertions)]
    {
        let source = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        if !binary.is_file() {
            binary = source.join("binaries").join(format!(
                "mdtero-connect-bridge-{}{suffix}",
                env!("MDTERO_NATIVE_TARGET")
            ));
        }
        if !runtime.is_dir() {
            runtime = source.join("resources/runtime");
        }
    }
    if !binary.is_file() || !runtime.is_dir() {
        return Err("bundled Connect resources are missing; run prepare.py".into());
    }
    let manifest: serde_json::Value =
        serde_json::from_slice(&std::fs::read(runtime.join("manifest.json"))?)?;
    if manifest["product"] != "mdtero-connect-debug"
        || manifest["protocol"] != 1
        || manifest["target"] != env!("MDTERO_NATIVE_TARGET")
    {
        return Err("bundled runtime manifest does not match this client".into());
    }
    let full = match manifest["edition"].as_str() {
        Some("full") => true,
        Some("basic") => false,
        _ => return Err("invalid bundled edition".into()),
    };
    Ok((binary, runtime, full))
}

fn status(app: &tauri::AppHandle, message: &str) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_title(&format!("Mdtero Connect Debug · {message}"));
        // Only native fixed messages enter this expression. No sidecar output is evaluated.
        let literal = serde_json::to_string(message).unwrap();
        let _ = window.eval(&format!("document.getElementById('status')?.replaceChildren(document.createTextNode({literal}))"));
    }
}

fn start_bridge(app: tauri::AppHandle) {
    let state = app.state::<NativeState>();
    let mut slot = state.bridge.lock().unwrap();
    let generation = state.generation.fetch_add(1, Ordering::SeqCst) + 1;
    let old = slot.take();
    drop(old);
    if state.exiting.load(Ordering::SeqCst) {
        return;
    }
    let (child, ready) = match ManagedChild::launch(&state.binary, &state.runtime, state.full) {
        Ok(value) => value,
        Err(_) => {
            status(&app, "本机桥接启动失败，请检查调试构建资源");
            return;
        }
    };
    let pid = child.pid();
    *slot = Some(child);
    drop(slot);
    drop(state);
    std::thread::spawn(move || {
        let result = ready.recv_timeout(Duration::from_secs(60));
        let state = app.state::<NativeState>();
        if state.exiting.load(Ordering::SeqCst)
            || generation != state.generation.load(Ordering::SeqCst)
        {
            return;
        }
        match result {
            Ok(Ok(url)) => {
                *state.origin.lock().unwrap() = Some(url.clone());
                if let Some(window) = app.get_webview_window("main") {
                    if window.navigate(url.clone()).is_err() {
                        status(&app, "无法载入本机页面");
                    } else {
                        let _ = window.set_title("Mdtero Connect Debug");
                    }
                }
                println!(
                    "{}",
                    serde_json::json!({"event":"bridge_ready","port":url.port(),"pid":pid})
                );
            }
            _ => {
                let child = state.bridge.lock().unwrap().take();
                drop(child);
                status(&app, "本机桥接未就绪，请退出后重试");
            }
        }
    });
}

fn login(app: tauri::AppHandle) {
    let state = app.state::<NativeState>();
    let mut slot = state.login.lock().unwrap();
    if slot.is_some() || state.exiting.load(Ordering::SeqCst) {
        return;
    }
    let generation = state.login_generation.fetch_add(1, Ordering::SeqCst) + 1;
    let (child, ready) = match ManagedChild::login(&state.binary) {
        Ok(value) => value,
        Err(_) => {
            status(&app, "无法启动登录，请重试");
            return;
        }
    };
    *slot = Some(child);
    drop(slot);
    status(&app, "正在系统浏览器登录；可从菜单取消");
    std::thread::spawn(move || {
        let result = ready.recv_timeout(Duration::from_secs(360));
        let state = app.state::<NativeState>();
        let mut slot = state.login.lock().unwrap();
        if generation != state.login_generation.load(Ordering::SeqCst) {
            return;
        }
        let child = slot.take();
        drop(slot);
        let was_active = child.is_some();
        drop(child);
        if state.exiting.load(Ordering::SeqCst) || !was_active {
            return;
        }
        let authenticated = result
            .ok()
            .and_then(Result::ok)
            .and_then(|line| serde_json::from_str::<serde_json::Value>(&line).ok())
            .is_some_and(|v| {
                v["protocol"] == 1
                    && v["product"] == "mdtero-connect"
                    && v["status"] == "authenticated"
            });
        if authenticated {
            start_bridge(app.clone());
        } else {
            status(&app, "登录未完成，可从菜单重试");
        }
    });
}

fn export_dir(app: &tauri::AppHandle) -> Option<PathBuf> {
    let path = app.path().download_dir().ok()?.join("Mdtero Connect");
    std::fs::create_dir_all(&path).ok()?;
    Some(path)
}

fn open_external(url: &Url) {
    if matches!(url.scheme(), "https" | "http")
        && url.username().is_empty()
        && url.password().is_none()
    {
        let _ = open::that(url.as_str());
    }
}

pub fn run() {
    let smoke_export = std::env::args().any(|arg| arg == "--smoke-export");
    let smoke = smoke_export || std::env::args().any(|arg| arg == "--smoke-test");
    let app = tauri::Builder::default()
        .setup(move |app| {
            let (binary, runtime, full) = resources(app.handle())?;
            app.manage(NativeState {
                bridge: Mutex::new(None),
                login: Mutex::new(None),
                origin: Mutex::new(None),
                binary,
                runtime,
                full,
                exiting: AtomicBool::new(false),
                generation: AtomicU64::new(0),
                login_generation: AtomicU64::new(0),
                smoke_download: Mutex::new(None),
            });
            let handle = app.handle().clone();
            let nav = handle.clone();
            let downloads = handle.clone();
            let window = WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::App("index.html".into()),
            )
            .title("Mdtero Connect Debug")
            .inner_size(1200.0, 820.0)
            .min_inner_size(840.0, 600.0)
            .on_navigation(move |url| {
                let state = nav.state::<NativeState>();
                let allowed = allow_navigation(url, state.origin.lock().unwrap().as_ref());
                if !allowed {
                    open_external(url);
                }
                allowed
            })
            .on_new_window(|url, _| {
                open_external(&url);
                NewWindowResponse::Deny
            })
            .on_download(move |_, event| match event {
                DownloadEvent::Requested { url, destination } => {
                    let state = downloads.state::<NativeState>();
                    if !state
                        .origin
                        .lock()
                        .unwrap()
                        .as_ref()
                        .is_some_and(|origin| allow_navigation(&url, Some(origin)))
                    {
                        return false;
                    }
                    let Some(folder) = export_dir(&downloads) else {
                        return false;
                    };
                    static SERIAL: AtomicU64 = AtomicU64::new(0);
                    let millis = SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_millis();
                    *destination = folder.join(format!(
                        "{millis}-{}-{}",
                        SERIAL.fetch_add(1, Ordering::Relaxed),
                        safe_filename(destination)
                    ));
                            if smoke_export { *state.smoke_download.lock().unwrap() = Some(destination.clone()); }
                    true
                }
                DownloadEvent::Finished { success, .. } => {
                    println!(
                        "{}",
                        serde_json::json!({"event":"export_finished","success":success})
                    );
                            if smoke_export {
                                let path = downloads.state::<NativeState>().smoke_download.lock().unwrap().take();
                                let verified = success && path.as_ref().is_some_and(|path| std::fs::read(path).ok().as_deref() == Some(SMOKE_EXPORT.as_bytes()));
                                if let Some(path) = path { let _ = std::fs::remove_file(path); }
                                println!("{}", serde_json::json!({"event":"native_export_smoke_passed","verified_bytes":verified}));
                                downloads.exit(if verified { 0 } else { 3 });
                            }
                    true
                }
                _ => false,
            })
            .on_page_load(move |window, event| {
                let state = window.state::<NativeState>();
                if smoke
                    && event.event() == PageLoadEvent::Finished
                    && state
                        .origin
                        .lock()
                        .unwrap()
                        .as_ref()
                        .is_some_and(|origin| same_bridge(event.url(), origin))
                {
                    println!(
                        "{}",
                        serde_json::json!({"event":"native_smoke_passed","webview_loaded":true})
                    );
                        if smoke_export {
                            let literal = serde_json::to_string(SMOKE_EXPORT).unwrap();
                            let script = format!("(()=>{{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([{literal}],{{type:'text/plain'}}));a.download='mdtero-native-smoke.bib';document.body.append(a);a.click();a.remove();}})()");
                            if window.eval(&script).is_err() { window.app_handle().exit(3); }
                        } else { window.app_handle().exit(0); }
                }
            })
            .build()?;
            let close = handle.clone();
            window.on_window_event(move |event| {
                if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                    close.exit(0);
                }
            });
            use tauri::menu::{Menu, SubmenuBuilder};
            let menu = Menu::default(&handle)?;
            menu.append(
                &SubmenuBuilder::new(&handle, "Connect")
                    .text("login", "登录 Mdtero 账户…")
                    .text("cancel-login", "取消登录")
                    .separator()
                    .text("exports", "打开导出文件夹")
                    .text("reload", "重新连接本机桥接")
                    .build()?,
            )?;
            app.set_menu(menu)?;
            app.on_menu_event(|app, event| match event.id().as_ref() {
                "login" => login(app.clone()),
                "cancel-login" => {
                    let state = app.state::<NativeState>();
                    let mut slot = state.login.lock().unwrap();
                    state.login_generation.fetch_add(1, Ordering::SeqCst);
                    let child = slot.take();
                    drop(slot);
                    drop(child);
                    status(app, "已取消登录");
                }
                "exports" => {
                    if let Some(path) = export_dir(app) {
                        let _ = open::that(path);
                    }
                }
                "reload" => start_bridge(app.clone()),
                _ => (),
            });
            start_bridge(handle.clone());
            if smoke {
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_secs(75));
                    handle.exit(2);
                });
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Could not initialize the Connect debug client");
    app.run(|app, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            let state = app.state::<NativeState>();
            state.exiting.store(true, Ordering::SeqCst);
            let login = state.login.lock().unwrap().take();
            let bridge = state.bridge.lock().unwrap().take();
            drop(login);
            drop(bridge);
        }
    });
}
