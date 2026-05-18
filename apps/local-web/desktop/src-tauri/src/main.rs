//! Input: 环境变量（LMCA_BACKEND_PORT 等）  |  Output: Tauri 桌面窗口 + 子进程生命周期
//! Role: 桌面层入口，负责启动 Python 后端、解析前端目标、构建 Tauri 窗口并注入 API 桥接
//! Note: 生产模式加载打包资源，调试模式连接外部 Vite 开发服务器；前端 URL 必须为回环地址
//! Usage: 由 Tauri CLI（cargo tauri dev / tauri build）编译后直接运行，不应手动调用
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod data_directory;
mod diagnostics;
mod instance_guard;
mod runtime;
mod runtime_layout;

use crate::diagnostics::startup_failure_html;
use crate::instance_guard::{try_acquire_instance_guard, ActiveInstanceGuard, InstanceGuardResult};
use crate::runtime::{
    build_initialization_script, clamp_fallback_attempts, launch_backend_and_wait, RuntimeConfig,
    RuntimeState, StartupFailure,
};
use crate::runtime_layout::{
    app_data_root_for_mode, resolve_runtime_layout, resolve_runtime_mode, RuntimeLayoutInputs,
    RuntimeMode,
};
use std::env;
use std::error::Error;
use std::path::{Path, PathBuf};
use std::process::Child;
use std::sync::Mutex;
use std::time::Duration;
use tauri::api::path::local_data_dir;
use tauri::{AppHandle, Manager, RunEvent, WindowBuilder, WindowUrl};
use url::form_urlencoded::byte_serialize;
use url::Url;

const MAIN_WINDOW_LABEL: &str = "main";
const STARTUP_FAILURE_WINDOW_LABEL: &str = "startup-failure";
const INSTANCE_GUARD_TIMEOUT: Duration = Duration::from_millis(500);

#[derive(Default)]
struct BackendProcessState(Mutex<Option<Child>>);

#[derive(Default)]
struct InstanceGuardState(Mutex<Option<ActiveInstanceGuard>>);

#[derive(Default)]
struct PendingWindowFocusState(Mutex<bool>);

#[derive(Clone)]
pub struct DataDirectoryCommandState {
    pub runtime_mode: RuntimeMode,
    pub config_root: PathBuf,
    pub default_app_data_root: PathBuf,
    pub current_app_data_root: PathBuf,
    pub resource_root: Option<PathBuf>,
}

struct LoadedRuntimeConfig {
    runtime_config: RuntimeConfig,
    data_directory_command_state: DataDirectoryCommandState,
}

struct BackendChildCleanup(Option<Child>);

#[derive(Debug, PartialEq)]
enum FrontendLaunchTarget {
    BundledApp,
    External(Url),
}

impl FrontendLaunchTarget {
    fn into_window_url(self) -> WindowUrl {
        match self {
            Self::BundledApp => WindowUrl::App("index.html".into()),
            Self::External(url) => WindowUrl::External(url),
        }
    }
}

impl BackendChildCleanup {
    fn new(child: Child) -> Self {
        Self(Some(child))
    }

    fn take(&mut self) -> Option<Child> {
        self.0.take()
    }
}

impl Drop for BackendChildCleanup {
    fn drop(&mut self) {
        if let Some(mut child) = self.0.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

enum RuntimeConfigLoadResult {
    Ready(LoadedRuntimeConfig),
    ExistingInstanceNotified,
}

enum PendingMigrationSourceGuardResult {
    NoPending,
    Guard(ActiveInstanceGuard),
    ExistingInstanceNotified,
}

fn main() {
    if cfg!(debug_assertions) {
        eprintln!("desktop: builder starting");
    }
    tauri::Builder::default()
        .manage(BackendProcessState::default())
        .manage(InstanceGuardState::default())
        .manage(PendingWindowFocusState::default())
        .invoke_handler(tauri::generate_handler![
            data_directory::lmca_get_data_directory_state,
            data_directory::lmca_choose_data_directory,
            data_directory::lmca_schedule_data_directory_migration,
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                eprintln!("desktop: setup entered");
            }
            let loaded = match load_runtime_config(app) {
                Ok(RuntimeConfigLoadResult::Ready(loaded)) => loaded,
                Ok(RuntimeConfigLoadResult::ExistingInstanceNotified) => {
                    app.handle().exit(0);
                    return Ok(());
                }
                Err(startup_failure) => {
                    let data_url = data_url_from_html(&startup_failure_html(
                        &startup_failure.user_message,
                        &startup_failure.diagnostics,
                    ))?;

                    WindowBuilder::new(app, "startup-failure", WindowUrl::External(data_url))
                        .title("AI Memory Card Startup Failed")
                        .inner_size(760.0, 540.0)
                        .min_inner_size(640.0, 480.0)
                        .resizable(true)
                        .build()?;
                    let _ = try_apply_pending_window_focus(&app.handle());
                    return Ok(());
                }
            };
            app.manage(loaded.data_directory_command_state.clone());
            let config = loaded.runtime_config;
            let app_handle = app.handle();
            match try_acquire_instance_guard(
                &config.app_data_dir,
                INSTANCE_GUARD_TIMEOUT,
                move || request_window_focus(app_handle.clone()),
            ) {
                Ok(InstanceGuardResult::ExistingInstanceNotified) => {
                    app.handle().exit(0);
                    return Ok(());
                }
                Ok(InstanceGuardResult::Primary(instance_guard)) => {
                    let state = app.state::<InstanceGuardState>();
                    let mut guard_slot = state.0.lock().expect("instance guard state should lock");
                    *guard_slot = Some(instance_guard);
                }
                Err(error) => {
                    let startup_failure = instance_guard_startup_failure(
                        &config,
                        format!("Failed to initialize the per-data-root instance guard: {error}"),
                    );
                    let data_url = data_url_from_html(&startup_failure_html(
                        &startup_failure.user_message,
                        &startup_failure.diagnostics,
                    ))?;

                    WindowBuilder::new(
                        app,
                        STARTUP_FAILURE_WINDOW_LABEL,
                        WindowUrl::External(data_url),
                    )
                    .title("AI Memory Card Startup Failed")
                    .inner_size(760.0, 540.0)
                    .min_inner_size(640.0, 480.0)
                    .resizable(true)
                    .build()?;
                    let _ = try_apply_pending_window_focus(&app.handle());
                    return Ok(());
                }
            }
            match launch_backend_and_wait(config) {
                Ok(runtime_state) => {
                    if cfg!(debug_assertions) {
                        eprintln!("desktop: backend launch reported ready");
                    }
                    let RuntimeState {
                        backend_url,
                        diagnostics,
                        child,
                    } = runtime_state;
                    let mut backend_child = BackendChildCleanup::new(child);
                    let mut diagnostics = diagnostics;
                    if let Some(focus_port) = active_focus_port(app) {
                        diagnostics.set_focus_port(focus_port);
                    }
                    let frontend_target = match resolve_frontend_launch_target(
                        diagnostics.frontend_url.as_str(),
                        use_external_frontend_runtime(),
                    ) {
                        Ok(target) => target,
                        Err(error_message) => {
                            diagnostics.mark_failed("frontend_target", &error_message);
                            let data_url = data_url_from_html(&startup_failure_html(
                                &error_message,
                                &diagnostics,
                            ))?;

                            WindowBuilder::new(
                                app,
                                STARTUP_FAILURE_WINDOW_LABEL,
                                WindowUrl::External(data_url),
                            )
                            .title("AI Memory Card Startup Failed")
                            .inner_size(760.0, 540.0)
                            .min_inner_size(640.0, 480.0)
                            .resizable(true)
                            .build()?;
                            let _ = try_apply_pending_window_focus(&app.handle());
                            return Ok(());
                        }
                    };

                    let initialization_script =
                        build_initialization_script(&backend_url, &diagnostics);

                    if cfg!(debug_assertions) {
                        eprintln!("desktop: building main window");
                    }
                    WindowBuilder::new(app, MAIN_WINDOW_LABEL, frontend_target.into_window_url())
                        .title("AI Memory Card")
                        .inner_size(1280.0, 860.0)
                        .min_inner_size(960.0, 640.0)
                        .initialization_script(&initialization_script)
                        .build()?;
                    let _ = try_apply_pending_window_focus(&app.handle());
                    if cfg!(debug_assertions) {
                        eprintln!("desktop: main window built");
                    }

                    let state = app.state::<BackendProcessState>();
                    let mut child_slot = state.0.lock().expect("backend child state should lock");
                    *child_slot =
                        Some(backend_child.take().expect(
                            "backend child should still be available after window creation",
                        ));
                }
                Err(mut startup_failure) => {
                    if cfg!(debug_assertions) {
                        eprintln!("desktop: startup failure path");
                        eprintln!("{}", startup_failure.user_message);
                        eprintln!("{}", startup_failure.diagnostics.to_pretty_json());
                    }
                    if let Some(focus_port) = active_focus_port(app) {
                        startup_failure.diagnostics.set_focus_port(focus_port);
                    }
                    let data_url = data_url_from_html(&startup_failure_html(
                        &startup_failure.user_message,
                        &startup_failure.diagnostics,
                    ))?;

                    WindowBuilder::new(
                        app,
                        STARTUP_FAILURE_WINDOW_LABEL,
                        WindowUrl::External(data_url),
                    )
                    .title("AI Memory Card Startup Failed")
                    .inner_size(760.0, 540.0)
                    .min_inner_size(640.0, 480.0)
                    .resizable(true)
                    .build()?;
                    let _ = try_apply_pending_window_focus(&app.handle());
                }
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build tauri desktop shell")
        .run(|app_handle, event| {
            if cfg!(debug_assertions) {
                eprintln!("desktop: run event -> {:?}", event);
            }
            if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
                shutdown_backend(app_handle);
                shutdown_instance_guard(app_handle);
            }
        });
}

fn load_runtime_config<R: tauri::Runtime>(
    app: &tauri::App<R>,
) -> Result<RuntimeConfigLoadResult, StartupFailure> {
    let preferred_port = env::var("LMCA_BACKEND_PORT")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(8000);
    let fallback_attempts = env::var("LMCA_BACKEND_FALLBACK_ATTEMPTS")
        .ok()
        .and_then(|value| value.parse().ok())
        .map(clamp_fallback_attempts)
        .unwrap_or(5);
    let health_timeout_ms = env::var("LMCA_HEALTH_TIMEOUT_MS")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(15_000);
    let use_external_frontend = use_external_frontend_runtime();
    let frontend_url = if use_external_frontend {
        env_or_default("LMCA_FRONTEND_URL", default_frontend_url(true))
    } else {
        default_frontend_url(false).to_string()
    };
    let backend_root_override = env::var("LMCA_BACKEND_ROOT").ok().map(PathBuf::from);
    let python_command_override = env::var("LMCA_BACKEND_PYTHON").ok();
    let runtime_mode_override = env::var("LMCA_RUNTIME_MODE").ok();
    let resource_dir = app.path_resolver().resource_dir();
    let local_data_dir = local_data_dir();
    let runtime_mode =
        resolve_runtime_mode(cfg!(debug_assertions), runtime_mode_override.as_deref()).map_err(
            |error_message| {
                runtime_layout_startup_failure(
                    frontend_url.clone(),
                    backend_root_override.clone(),
                    runtime_mode_override.clone(),
                    resource_dir.clone(),
                    preferred_port,
                    health_timeout_ms,
                    error_message,
                )
            },
        )?;
    let repo_backend_root = repo_backend_root_for_mode(runtime_mode);
    let data_config_root = local_data_dir
        .as_ref()
        .map(|path| path.join("AIMemoryCard"))
        .ok_or_else(|| {
            runtime_layout_startup_failure(
                frontend_url.clone(),
                backend_root_override.clone(),
                runtime_mode_override.clone(),
                resource_dir.clone(),
                preferred_port,
                health_timeout_ms,
                "Unable to determine the OS local data directory for data directory config"
                    .to_string(),
            )
        })?;
    let default_app_data_root = app_data_root_for_mode(runtime_mode, local_data_dir.as_deref())
        .ok_or_else(|| {
            runtime_layout_startup_failure(
                frontend_url.clone(),
                backend_root_override.clone(),
                runtime_mode_override.clone(),
                resource_dir.clone(),
                preferred_port,
                health_timeout_ms,
                "Unable to determine the default app data directory".to_string(),
            )
        })?;
    let pending_source_guard = match acquire_pending_migration_source_guard(
        runtime_mode,
        &data_config_root,
        INSTANCE_GUARD_TIMEOUT,
        || {},
    )
    .map_err(|error_message| {
        runtime_layout_startup_failure(
            frontend_url.clone(),
            backend_root_override.clone(),
            runtime_mode_override.clone(),
            resource_dir.clone(),
            preferred_port,
            health_timeout_ms,
            format!("Data directory migration failed: {error_message}"),
        )
    })? {
        PendingMigrationSourceGuardResult::NoPending => None,
        PendingMigrationSourceGuardResult::Guard(guard) => Some(guard),
        PendingMigrationSourceGuardResult::ExistingInstanceNotified => {
            return Ok(RuntimeConfigLoadResult::ExistingInstanceNotified)
        }
    };
    data_directory::apply_pending_migration(
        runtime_mode,
        &data_config_root,
        resource_dir.as_deref(),
    )
    .map_err(|error_message| {
        runtime_layout_startup_failure(
            frontend_url.clone(),
            backend_root_override.clone(),
            runtime_mode_override.clone(),
            resource_dir.clone(),
            preferred_port,
            health_timeout_ms,
            format!("Data directory migration failed: {error_message}"),
        )
    })?;
    drop(pending_source_guard);
    let resolved_layout = resolve_runtime_layout(RuntimeLayoutInputs {
        debug_assertions: cfg!(debug_assertions),
        repo_backend_root,
        local_data_dir: local_data_dir.clone(),
        resource_dir: resource_dir.clone(),
        backend_root_override: backend_root_override.clone(),
        python_command_override,
        runtime_mode_override: runtime_mode_override.clone(),
        data_config_root: Some(data_config_root.clone()),
    })
    .map_err(|error_message| {
        runtime_layout_startup_failure(
            frontend_url.clone(),
            backend_root_override.clone(),
            runtime_mode_override.clone(),
            resource_dir.clone(),
            preferred_port,
            health_timeout_ms,
            error_message,
        )
    })?;

    let data_directory_command_state = DataDirectoryCommandState {
        runtime_mode: resolved_layout.runtime_mode,
        config_root: data_config_root,
        default_app_data_root,
        current_app_data_root: resolved_layout.app_data_root.clone(),
        resource_root: resource_dir,
    };
    let runtime_config = RuntimeConfig {
        frontend_url,
        backend_root: resolved_layout.backend_root,
        python_command: resolved_layout.python_command,
        runtime_mode: resolved_layout.runtime_mode,
        app_data_dir: resolved_layout.app_data_root,
        database_url: resolved_layout.database_url,
        log_dir: resolved_layout.log_dir,
        cache_dir: resolved_layout.cache_dir,
        plugin_root: resolved_layout.plugin_root,
        backend_host: "127.0.0.1".to_string(),
        preferred_port,
        fallback_attempts,
        health_timeout: Duration::from_millis(health_timeout_ms),
        poll_interval: Duration::from_millis(250),
    };

    if cfg!(debug_assertions) {
        eprintln!(
            "desktop: runtime config -> mode={:?}, backend_root={}, app_data_dir={}, plugin_root={}",
            runtime_config.runtime_mode,
            runtime_config.backend_root.display(),
            runtime_config.app_data_dir.display(),
            runtime_config.plugin_root.display(),
        );
    }

    Ok(RuntimeConfigLoadResult::Ready(LoadedRuntimeConfig {
        runtime_config,
        data_directory_command_state,
    }))
}

fn repo_backend_root_for_mode(runtime_mode: RuntimeMode) -> PathBuf {
    match runtime_mode {
        RuntimeMode::Dev => dev_backend_root(),
        RuntimeMode::Bundled => discover_backend_root().unwrap_or_else(dev_backend_root),
    }
}

fn acquire_pending_migration_source_guard<F>(
    runtime_mode: RuntimeMode,
    config_root: &Path,
    timeout: Duration,
    on_focus: F,
) -> Result<PendingMigrationSourceGuardResult, String>
where
    F: Fn() + Send + Sync + 'static,
{
    let pending = match data_directory::read_pending_migration(config_root, runtime_mode)? {
        Some(pending) => pending,
        None => return Ok(PendingMigrationSourceGuardResult::NoPending),
    };
    match try_acquire_instance_guard(&pending.source_app_data_root, timeout, on_focus) {
        Ok(InstanceGuardResult::ExistingInstanceNotified) => {
            Ok(PendingMigrationSourceGuardResult::ExistingInstanceNotified)
        }
        Ok(InstanceGuardResult::Primary(guard)) => {
            Ok(PendingMigrationSourceGuardResult::Guard(guard))
        }
        Err(error) => Err(format!(
            "Failed to guard source data directory {} before migration: {error}",
            pending.source_app_data_root.display()
        )),
    }
}

fn use_external_frontend_runtime() -> bool {
    cfg!(debug_assertions)
}

fn default_frontend_url(use_external_frontend: bool) -> &'static str {
    if use_external_frontend {
        "http://127.0.0.1:5173"
    } else {
        "app://index.html"
    }
}

fn discover_backend_root() -> Option<PathBuf> {
    env::current_exe()
        .ok()
        .and_then(|path| path.parent().and_then(resolve_backend_root_from))
}

fn resolve_backend_root_from(start_dir: &Path) -> Option<PathBuf> {
    resolve_backend_root_from_with(start_dir, is_backend_root)
}

fn resolve_backend_root_from_with(
    start_dir: &Path,
    is_backend_root: impl Fn(&Path) -> bool,
) -> Option<PathBuf> {
    start_dir.ancestors().find_map(|ancestor| {
        backend_root_candidates(ancestor)
            .into_iter()
            .find(|candidate| is_backend_root(candidate))
    })
}

fn backend_root_candidates(base_dir: &Path) -> [PathBuf; 3] {
    [
        base_dir.join("backend"),
        base_dir.join("resources").join("backend"),
        base_dir.join("Resources").join("backend"),
    ]
}

fn is_backend_root(path: &Path) -> bool {
    path.join("pyproject.toml").is_file() && path.join("app").join("main.py").is_file()
}

fn dev_backend_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../backend")
}

fn resolve_frontend_launch_target(
    frontend_url: &str,
    use_external_frontend: bool,
) -> Result<FrontendLaunchTarget, String> {
    if !use_external_frontend {
        return Ok(FrontendLaunchTarget::BundledApp);
    }

    let parsed_url = parse_url(frontend_url).map_err(|error| error.to_string())?;
    if !frontend_origin_is_localhost_or_loopback(&parsed_url) {
        return Err(
            "Frontend URL must be localhost or loopback before injecting the API bridge."
                .to_string(),
        );
    }

    Ok(FrontendLaunchTarget::External(parsed_url))
}

fn env_or_default(key: &str, default_value: &str) -> String {
    env::var(key).unwrap_or_else(|_| default_value.to_string())
}

fn runtime_layout_startup_failure(
    frontend_url: String,
    backend_root_override: Option<PathBuf>,
    runtime_mode_override: Option<String>,
    resource_dir: Option<PathBuf>,
    preferred_port: u16,
    health_timeout_ms: u64,
    error_message: String,
) -> StartupFailure {
    let runtime_mode =
        resolve_runtime_mode(cfg!(debug_assertions), runtime_mode_override.as_deref()).unwrap_or(
            if cfg!(debug_assertions) {
                RuntimeMode::Dev
            } else {
                RuntimeMode::Bundled
            },
        );
    let app_data_root =
        app_data_root_for_mode(runtime_mode, local_data_dir().as_deref()).unwrap_or_default();
    let backend_root = backend_root_override.unwrap_or_else(|| match runtime_mode {
        RuntimeMode::Dev => repo_backend_root_for_mode(RuntimeMode::Dev),
        RuntimeMode::Bundled => resource_dir.unwrap_or_default().join("backend"),
    });
    let mut diagnostics = crate::diagnostics::RuntimeDiagnostics::new(
        runtime_mode,
        frontend_url,
        backend_root.display().to_string(),
        app_data_root.display().to_string(),
        "127.0.0.1".to_string(),
        preferred_port,
        health_timeout_ms,
    );
    diagnostics.mark_failed("runtime_layout", &error_message);

    StartupFailure {
        user_message: crate::diagnostics::friendly_failure_message(&diagnostics),
        diagnostics,
    }
}

fn data_url_from_html(html: &str) -> Result<Url, url::ParseError> {
    let encoded = byte_serialize(html.as_bytes()).collect::<String>();
    Url::parse(&format!("data:text/html;charset=utf-8,{encoded}"))
}

fn instance_guard_startup_failure(config: &RuntimeConfig, error_message: String) -> StartupFailure {
    let mut diagnostics = crate::diagnostics::RuntimeDiagnostics::new(
        config.runtime_mode,
        config.frontend_url.clone(),
        config.backend_root.display().to_string(),
        config.app_data_dir.display().to_string(),
        config.backend_host.clone(),
        config.preferred_port,
        config.health_timeout.as_millis() as u64,
    );
    diagnostics.mark_failed("instance_guard", &error_message);

    StartupFailure {
        user_message: crate::diagnostics::friendly_failure_message(&diagnostics),
        diagnostics,
    }
}

fn parse_url(value: &str) -> Result<Url, Box<dyn Error>> {
    Ok(Url::parse(value)?)
}

fn frontend_origin_is_localhost_or_loopback(url: &Url) -> bool {
    matches!(url.scheme(), "http" | "https")
        && match url.host() {
            Some(url::Host::Domain("localhost")) => true,
            Some(url::Host::Ipv4(ip)) => ip.is_loopback(),
            Some(url::Host::Ipv6(ip)) => ip.is_loopback(),
            Some(url::Host::Domain(_)) | None => false,
        }
}

fn shutdown_backend(app_handle: &AppHandle) {
    let state = app_handle.state::<BackendProcessState>();
    let lock_result = state.0.lock();
    if let Ok(mut child_slot) = lock_result {
        if let Some(child) = child_slot.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *child_slot = None;
    }
}

fn active_focus_port<R: tauri::Runtime>(app: &tauri::App<R>) -> Option<u16> {
    let state = app.state::<InstanceGuardState>();
    let guard_slot = state.0.lock().ok()?;
    guard_slot.as_ref().map(|guard| guard.metadata().focus_port)
}

fn request_window_focus<R: tauri::Runtime>(app_handle: AppHandle<R>) {
    let pending_focus_state = app_handle.state::<PendingWindowFocusState>();
    mark_pending_window_focus(&pending_focus_state.0);
    let focus_handle = app_handle.clone();
    let _ = app_handle.run_on_main_thread(move || {
        let _ = try_apply_pending_window_focus(&focus_handle);
    });
}

fn focus_existing_window<R: tauri::Runtime>(app_handle: &AppHandle<R>) -> bool {
    if let Some(window) = app_handle
        .get_window(MAIN_WINDOW_LABEL)
        .or_else(|| app_handle.get_window(STARTUP_FAILURE_WINDOW_LABEL))
    {
        if window.is_minimized().unwrap_or(false) {
            let _ = window.unminimize();
        }
        let _ = window.show();
        let _ = window.set_focus();
        true
    } else {
        false
    }
}

fn mark_pending_window_focus(pending_focus: &Mutex<bool>) {
    if let Ok(mut pending_focus) = pending_focus.lock() {
        *pending_focus = true;
    }
}

fn try_consume_pending_window_focus(
    pending_focus: &Mutex<bool>,
    focus_action: impl FnOnce() -> bool,
) -> bool {
    let should_focus = match pending_focus.lock() {
        Ok(pending_focus) => *pending_focus,
        Err(_) => false,
    };
    if !should_focus {
        return false;
    }
    if !focus_action() {
        return false;
    }

    if let Ok(mut pending_focus) = pending_focus.lock() {
        *pending_focus = false;
    }
    true
}

fn try_apply_pending_window_focus<R: tauri::Runtime>(app_handle: &AppHandle<R>) -> bool {
    let pending_focus_state = app_handle.state::<PendingWindowFocusState>();
    try_consume_pending_window_focus(&pending_focus_state.0, || focus_existing_window(app_handle))
}

fn shutdown_instance_guard(app_handle: &AppHandle) {
    let state = app_handle.state::<InstanceGuardState>();
    let lock_result = state.0.lock();
    if let Ok(mut guard_slot) = lock_result {
        if let Some(guard) = guard_slot.as_mut() {
            let _ = guard.cleanup();
        }
        *guard_slot = None;
    }
}

#[cfg(test)]
mod tests {
    use super::{
        acquire_pending_migration_source_guard, default_frontend_url, dev_backend_root,
        frontend_origin_is_localhost_or_loopback, mark_pending_window_focus,
        repo_backend_root_for_mode, resolve_backend_root_from_with, resolve_frontend_launch_target,
        try_consume_pending_window_focus, FrontendLaunchTarget, PendingMigrationSourceGuardResult,
        RuntimeMode,
    };
    use crate::data_directory::{pending_migration_path, PendingDataMigration};
    use crate::instance_guard::{try_acquire_instance_guard, InstanceGuardResult};
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::{Arc, Mutex};
    use std::time::Duration;
    use url::Url;

    #[test]
    fn frontend_origin_allows_loopback_hosts_only() {
        assert!(frontend_origin_is_localhost_or_loopback(
            &Url::parse("http://localhost:5173").unwrap()
        ));
        assert!(frontend_origin_is_localhost_or_loopback(
            &Url::parse("http://127.0.0.1:5173").unwrap()
        ));
        assert!(frontend_origin_is_localhost_or_loopback(
            &Url::parse("http://[::1]:5173").unwrap()
        ));
        assert!(!frontend_origin_is_localhost_or_loopback(
            &Url::parse("http://example.com:5173").unwrap()
        ));
    }

    #[test]
    fn production_frontend_target_uses_bundled_assets() {
        let target = resolve_frontend_launch_target("http://example.com:5173", false).unwrap();

        assert_eq!(target, FrontendLaunchTarget::BundledApp);
        assert_eq!(default_frontend_url(false), "app://index.html");
    }

    #[test]
    fn backend_root_resolution_prefers_backend_adjacent_to_runtime_ancestors() {
        let expected = PathBuf::from("D:/repo/apps/local-web/backend");
        let resolved = resolve_backend_root_from_with(
            Path::new("D:/repo/apps/local-web/desktop/src-tauri/target/debug"),
            |candidate| candidate == expected,
        );

        assert_eq!(resolved, Some(expected));
    }

    #[test]
    fn dev_runtime_mode_uses_repo_backend_root_instead_of_target_copy() {
        let resolved = repo_backend_root_for_mode(RuntimeMode::Dev);
        let expected = dev_backend_root();

        assert_eq!(resolved, expected);
        assert!(!resolved.to_string_lossy().contains("src-tauri/target/debug/backend"));
    }

    #[test]
    fn pending_window_focus_stays_set_until_a_window_can_be_focused() {
        let pending_focus = Mutex::new(false);
        let focus_attempts = AtomicUsize::new(0);

        mark_pending_window_focus(&pending_focus);

        let focused = try_consume_pending_window_focus(&pending_focus, || {
            focus_attempts.fetch_add(1, Ordering::SeqCst);
            false
        });

        assert!(!focused);
        assert_eq!(focus_attempts.load(Ordering::SeqCst), 1);
        assert_eq!(
            *pending_focus.lock().expect("pending focus should lock"),
            true
        );
    }

    #[test]
    fn pending_window_focus_clears_after_focus_is_applied() {
        let pending_focus = Mutex::new(false);
        let focus_attempts = AtomicUsize::new(0);

        mark_pending_window_focus(&pending_focus);

        let focused = try_consume_pending_window_focus(&pending_focus, || {
            focus_attempts.fetch_add(1, Ordering::SeqCst);
            true
        });

        assert!(focused);
        assert_eq!(focus_attempts.load(Ordering::SeqCst), 1);
        assert_eq!(
            *pending_focus.lock().expect("pending focus should lock"),
            false
        );
    }

    #[test]
    fn pending_migration_source_guard_notifies_live_source_instance() {
        let config_root = unique_temp_dir("pending-source-config");
        let source_root = unique_temp_dir("pending-source-root");
        let target_root = unique_temp_dir("pending-target-root");
        fs::create_dir_all(&config_root).expect("config root should create");
        let pending = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: source_root.clone(),
            target_app_data_root: target_root.clone(),
            created_at: "2026-04-24T10:00:00Z".to_string(),
        };
        fs::write(
            pending_migration_path(&config_root, RuntimeMode::Bundled),
            serde_json::to_vec(&pending).expect("pending migration should serialize"),
        )
        .expect("pending migration should write");

        let focus_count = Arc::new(AtomicUsize::new(0));
        let live_focus_count = Arc::clone(&focus_count);
        let mut live_guard =
            match try_acquire_instance_guard(&source_root, Duration::from_millis(250), move || {
                live_focus_count.fetch_add(1, Ordering::SeqCst);
            })
            .expect("source guard should initialize")
            {
                InstanceGuardResult::Primary(guard) => guard,
                InstanceGuardResult::ExistingInstanceNotified => {
                    panic!("test source guard should be primary")
                }
            };

        let result = acquire_pending_migration_source_guard(
            RuntimeMode::Bundled,
            &config_root,
            Duration::from_millis(250),
            || {},
        )
        .expect("pending source guard check should succeed");

        assert!(matches!(
            result,
            PendingMigrationSourceGuardResult::ExistingInstanceNotified
        ));
        assert_eq!(focus_count.load(Ordering::SeqCst), 1);

        live_guard.cleanup().expect("live guard should clean up");
        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&target_root);
    }

    fn unique_temp_dir(label: &str) -> PathBuf {
        let id = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("clock should be after unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("lmca-main-{label}-{}-{id}", std::process::id()))
    }

    fn remove_dir_if_exists(path: &Path) {
        let _ = fs::remove_dir_all(path);
    }
}
