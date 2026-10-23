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
    bridge_attempts: AtomicU64,
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
    if manifest["product"] != "mdtero-connect-desktop"
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
    show(app, message, "");
}

/// Show a fixed native message on the bootstrap page. `action` is "", "login" or "retry"
/// and selects which button is visible. Only native constant strings reach this script.
fn show(app: &tauri::AppHandle, message: &str, action: &str) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_title("mdtero 客户端");
        let literal = serde_json::to_string(message).unwrap();
        let action = serde_json::to_string(action).unwrap();
        let _ = window.eval(&format!("document.getElementById('status')?.replaceChildren(document.createTextNode({literal}));document.body.dataset.action={action}"));
    }
}

/// True when the Mdtero account key is configured (same sources as the CLI config).
fn has_account() -> bool {
    if std::env::var("MDTERO_API_KEY").is_ok_and(|v| !v.trim().is_empty()) {
        return true;
    }
    let dir = match std::env::var_os("MDTERO_CONFIG_DIR") {
        Some(dir) => PathBuf::from(dir),
        None => match std::env::var_os("XDG_CONFIG_HOME") {
            Some(base) => PathBuf::from(base).join("mdtero"),
            None => match std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE")) {
                Some(home) => PathBuf::from(home).join(".config").join("mdtero"),
                None => return false,
            },
        },
    };
    std::fs::read(dir.join("config.json"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<serde_json::Value>(&bytes).ok())
        .and_then(|v| v["api_key"].as_str().map(|k| !k.trim().is_empty()))
        .unwrap_or(false)
}

const BRIDGE_AUTO_RETRIES: u64 = 2;

fn bridge_failed(app: &tauri::AppHandle) {
    let state = app.state::<NativeState>();
    if state.exiting.load(Ordering::SeqCst) {
        return;
    }
    let attempt = state.bridge_attempts.fetch_add(1, Ordering::SeqCst) + 1;
    if attempt <= BRIDGE_AUTO_RETRIES {
        let wait = 2 * attempt;
        show(app, &format!("正在重新连接，{wait} 秒后自动重试。"), "");
        let app = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs(wait));
            start_bridge(app);
        });
    } else {
        show(app, "本机服务暂时没有启动成功。请点击重试；如果仍然失败，请重新打开 mdtero 客户端。", "retry");
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
            drop(slot);
            drop(state);
            bridge_failed(&app);
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
                        show(&app, "无法载入本机页面，请重试。", "retry");
                    } else {
                        state.bridge_attempts.store(0, Ordering::SeqCst);
                        let _ = window.set_title("mdtero 客户端");
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
                drop(state);
                bridge_failed(&app);
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
            show(&app, "无法打开登录页面，请重试。", "login");
            return;
        }
    };
    *slot = Some(child);
    drop(slot);
    show(&app, "请在打开的浏览器页面中登录 Mdtero 账户。", "");
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
            show(&app, "登录成功，正在进入…", "");
            start_bridge(app.clone());
        } else {
            show(&app, "登录没有完成。", "login");
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
                bridge_attempts: AtomicU64::new(0),
            });
            let handle = app.handle().clone();
            let nav = handle.clone();
            let downloads = handle.clone();
            let window = WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::App("index.html".into()),
            )
            .title("mdtero 客户端")
            .inner_size(1200.0, 820.0)
            .min_inner_size(840.0, 600.0)
            .on_navigation(move |url| {
                // Buttons on the bootstrap page; never a real navigation.
                if url.scheme() == "mdtero-action" {
                    match url.path() {
                        "login" => login(nav.clone()),
                        "retry" => {
                            nav.state::<NativeState>().bridge_attempts.store(0, Ordering::SeqCst);
                            show(&nav, "正在启动…", "");
                            start_bridge(nav.clone());
                        }
                        _ => (),
                    }
                    return false;
                }
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
                &SubmenuBuilder::new(&handle, "mdtero")
                    .text("login", "登录 mdtero 账户…")
                    .text("cancel-login", "取消登录")
                    .separator()
                    .text("exports", "打开导出文件夹")
                    .text("reload", "重新连接")
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
            if smoke || has_account() {
                start_bridge(handle.clone());
            } else {
                // First launch: go straight to account login; the bridge starts after it succeeds.
                show(&handle, "请先登录 mdtero 账户。", "login");
                login(handle.clone());
            }
            if smoke {
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_secs(75));
                    handle.exit(2);
                });
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Could not initialize Mdtero Connect");
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
