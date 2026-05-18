//! Input: RuntimeConfig（后端根目录、端口偏好、超时等）  |  Output: RuntimeState（进程句柄+URL）
//! Role: 桌面层运行时核心，负责端口探测、spawn Python uvicorn 进程、健康轮询直至就绪
//! Note: 最多尝试 MAX_BACKEND_FALLBACK_ATTEMPTS(50) 个候选端口；超时后强制终止子进程
//! Usage: 由 main.rs 在 Tauri setup 阶段调用 launch_backend_and_wait(config)
use crate::diagnostics::{friendly_failure_message, RuntimeDiagnostics};
use crate::runtime_layout::RuntimeMode;
use serde::Deserialize;
use std::collections::BTreeMap;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread::sleep;
use std::time::{Duration, Instant};

const DEFAULT_BACKEND_HOST: &str = "127.0.0.1";
pub const MAX_BACKEND_FALLBACK_ATTEMPTS: usize = 50;

#[derive(Debug)]
pub struct RuntimeConfig {
    pub frontend_url: String,
    pub backend_root: PathBuf,
    pub python_command: String,
    pub runtime_mode: RuntimeMode,
    pub app_data_dir: PathBuf,
    pub database_url: String,
    pub log_dir: PathBuf,
    pub cache_dir: PathBuf,
    pub plugin_root: PathBuf,
    pub backend_host: String,
    pub preferred_port: u16,
    pub fallback_attempts: usize,
    pub health_timeout: Duration,
    pub poll_interval: Duration,
}

impl RuntimeConfig {
    pub fn backend_url(&self, port: u16) -> String {
        format!("http://{}:{port}", self.backend_host)
    }

    pub fn health_url(&self, port: u16) -> String {
        format!("{}/api/health", self.backend_url(port))
    }

    pub fn candidate_ports(&self) -> Vec<u16> {
        candidate_ports(self.preferred_port, self.fallback_attempts)
    }

    pub fn backend_command(&self, port: u16) -> Vec<String> {
        vec![
            self.python_command.clone(),
            "-m".to_string(),
            "uvicorn".to_string(),
            "app.main:app".to_string(),
            "--host".to_string(),
            self.backend_host.clone(),
            "--port".to_string(),
            port.to_string(),
        ]
    }

    pub fn backend_environment(&self, port: u16) -> BTreeMap<String, String> {
        BTreeMap::from([
            ("LMCA_BACKEND_PORT".to_string(), port.to_string()),
            (
                "LMCA_RUNTIME_MODE".to_string(),
                self.runtime_mode.as_env_value().to_string(),
            ),
            (
                "LMCA_APP_DATA_DIR".to_string(),
                self.app_data_dir.display().to_string(),
            ),
            ("LMCA_DATABASE_URL".to_string(), self.database_url.clone()),
            (
                "LMCA_LOG_DIR".to_string(),
                self.log_dir.display().to_string(),
            ),
            (
                "LMCA_CACHE_DIR".to_string(),
                self.cache_dir.display().to_string(),
            ),
            (
                "LMCA_PLUGIN_ROOT".to_string(),
                self.plugin_root.display().to_string(),
            ),
        ])
    }
}

impl Default for RuntimeConfig {
    fn default() -> Self {
        Self {
            frontend_url: "http://127.0.0.1:5173".to_string(),
            backend_root: PathBuf::new(),
            python_command: "python".to_string(),
            runtime_mode: RuntimeMode::Dev,
            app_data_dir: PathBuf::new(),
            database_url: "sqlite:///./ai_memory_card.db".to_string(),
            log_dir: PathBuf::new(),
            cache_dir: PathBuf::new(),
            plugin_root: PathBuf::new(),
            backend_host: DEFAULT_BACKEND_HOST.to_string(),
            preferred_port: 8000,
            fallback_attempts: 5,
            health_timeout: Duration::from_secs(15),
            poll_interval: Duration::from_millis(250),
        }
    }
}

pub struct RuntimeState {
    pub backend_url: String,
    pub diagnostics: RuntimeDiagnostics,
    pub child: Child,
}

pub struct StartupFailure {
    pub user_message: String,
    pub diagnostics: RuntimeDiagnostics,
}

pub fn launch_backend_and_wait(config: RuntimeConfig) -> Result<RuntimeState, StartupFailure> {
    let mut diagnostics = RuntimeDiagnostics::new(
        config.runtime_mode,
        config.frontend_url.clone(),
        config.backend_root.display().to_string(),
        config.app_data_dir.display().to_string(),
        config.backend_host.clone(),
        config.preferred_port,
        config.health_timeout.as_millis() as u64,
    );

    let selected_port = match first_available_port(&config.candidate_ports(), port_is_available) {
        Some(port) => {
            for candidate in config.candidate_ports() {
                diagnostics.record_port_attempt(candidate);
                if candidate == port {
                    break;
                }
            }
            port
        }
        None => {
            let candidates = config.candidate_ports();
            for candidate in &candidates {
                diagnostics.record_port_attempt(*candidate);
            }
            diagnostics.mark_failed(
                "port_selection",
                "No available backend port was found in the fallback range",
            );
            return Err(StartupFailure {
                user_message: friendly_failure_message(&diagnostics),
                diagnostics,
            });
        }
    };

    diagnostics.select_port(selected_port);
    diagnostics.set_backend_command(config.backend_command(selected_port));

    let mut child = match spawn_backend(&config, selected_port) {
        Ok(child) => child,
        Err(error) => {
            diagnostics.mark_failed(
                "spawn_backend",
                format!("Failed to launch backend: {error}"),
            );
            return Err(StartupFailure {
                user_message: friendly_failure_message(&diagnostics),
                diagnostics,
            });
        }
    };

    diagnostics.set_child_pid(child.id());
    let health_url = config.health_url(selected_port);
    let deadline = Instant::now() + config.health_timeout;

    while Instant::now() <= deadline {
        diagnostics.record_health_check();

        if health_check_ok(&health_url) {
            diagnostics.mark_ready();
            return Ok(RuntimeState {
                backend_url: config.backend_url(selected_port),
                diagnostics,
                child,
            });
        }

        match child.try_wait() {
            Ok(Some(status)) => {
                let status = reap_child(&mut child).unwrap_or(status);
                diagnostics.mark_failed(
                    "backend_exited",
                    format!("Backend process exited before health was ready: {status}"),
                );
                return Err(StartupFailure {
                    user_message: friendly_failure_message(&diagnostics),
                    diagnostics,
                });
            }
            Ok(None) => {}
            Err(error) => {
                terminate_child(&mut child);
                diagnostics.mark_failed(
                    "backend_monitor",
                    format!("Failed to monitor backend process state: {error}"),
                );
                return Err(StartupFailure {
                    user_message: friendly_failure_message(&diagnostics),
                    diagnostics,
                });
            }
        }

        sleep(config.poll_interval);
    }

    terminate_child(&mut child);
    diagnostics.mark_failed(
        "health_timeout",
        format!(
            "Timed out waiting {} ms for backend health at {health_url}",
            config.health_timeout.as_millis()
        ),
    );
    Err(StartupFailure {
        user_message: friendly_failure_message(&diagnostics),
        diagnostics,
    })
}

pub fn build_initialization_script(backend_url: &str, diagnostics: &RuntimeDiagnostics) -> String {
    let backend_url_json = serde_json::to_string(backend_url)
        .unwrap_or_else(|_| "\"http://127.0.0.1:8000\"".to_string());
    let diagnostics_json = diagnostics
        .to_pretty_json()
        .replace('\u{2028}', "\\u2028")
        .replace('\u{2029}', "\\u2029");

    format!(
        r#"
window.__LMCA_BACKEND_URL__ = {backend_url_json};
window.__LMCA_STARTUP_DIAGNOSTICS__ = {diagnostics_json};
const __lmcaNativeFetch = window.fetch.bind(window);
window.fetch = (input, init) => {{
  if (typeof input === "string" && input.startsWith("/api")) {{
    return __lmcaNativeFetch(window.__LMCA_BACKEND_URL__ + input, init);
  }}

  if (input instanceof Request) {{
    const requestUrl = new URL(input.url, window.location.href);
    if (requestUrl.origin === window.location.origin && requestUrl.pathname.startsWith("/api")) {{
      const redirected = new Request(
        window.__LMCA_BACKEND_URL__ + requestUrl.pathname + requestUrl.search,
        input,
      );
      return __lmcaNativeFetch(redirected, init);
    }}
  }}

  return __lmcaNativeFetch(input, init);
}};
"#
    )
}

pub fn clamp_fallback_attempts(fallback_attempts: usize) -> usize {
    fallback_attempts.clamp(1, MAX_BACKEND_FALLBACK_ATTEMPTS)
}

pub fn candidate_ports(preferred_port: u16, fallback_attempts: usize) -> Vec<u16> {
    let attempts = clamp_fallback_attempts(fallback_attempts);
    (0..attempts)
        .map(|offset| preferred_port.saturating_add(offset as u16))
        .collect()
}

pub fn first_available_port(
    candidate_ports: &[u16],
    is_available: impl Fn(u16) -> bool,
) -> Option<u16> {
    candidate_ports
        .iter()
        .copied()
        .find(|port| is_available(*port))
}

fn terminate_child(child: &mut Child) {
    let _ = child.kill();
    let _ = reap_child(child);
}

fn reap_child(child: &mut Child) -> std::io::Result<std::process::ExitStatus> {
    child.wait()
}

fn spawn_backend(config: &RuntimeConfig, port: u16) -> std::io::Result<Child> {
    let mut command = Command::new(&config.python_command);
    command
        .arg("-m")
        .arg("uvicorn")
        .arg("app.main:app")
        .arg("--host")
        .arg(&config.backend_host)
        .arg("--port")
        .arg(port.to_string())
        .current_dir(&config.backend_root)
        .stdout(if cfg!(debug_assertions) {
            Stdio::inherit()
        } else {
            Stdio::null()
        })
        .stderr(if cfg!(debug_assertions) {
            Stdio::inherit()
        } else {
            Stdio::null()
        });
    for (key, value) in config.backend_environment(port) {
        command.env(key, value);
    }
    command.spawn()
}

fn port_is_available(port: u16) -> bool {
    TcpListener::bind((DEFAULT_BACKEND_HOST, port))
        .map(|listener| {
            drop(listener);
            true
        })
        .unwrap_or(false)
}

fn health_check_ok(health_url: &str) -> bool {
    match ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_millis(1_000))
        .timeout(Duration::from_secs(1))
        .build()
        .get(health_url)
        .call()
    {
        Ok(response) => response
            .into_json::<HealthResponse>()
            .map(|payload| payload.status == "ok")
            .unwrap_or(false),
        Err(_) => false,
    }
}

#[derive(Debug, Deserialize)]
struct HealthResponse {
    status: String,
}

#[cfg(test)]
mod tests {
    use super::{build_initialization_script, candidate_ports, first_available_port, reap_child};
    use crate::diagnostics::RuntimeDiagnostics;
    use crate::runtime::RuntimeConfig;
    use crate::runtime_layout::RuntimeMode;
    use std::path::PathBuf;
    use std::process::Command;
    use std::thread::sleep;
    use std::time::Duration;

    #[test]
    fn candidate_ports_includes_sequential_fallbacks() {
        assert_eq!(candidate_ports(8000, 4), vec![8000, 8001, 8002, 8003]);
    }

    #[test]
    fn candidate_ports_clamps_fallback_attempts_to_safe_range() {
        let initial_ports = candidate_ports(8000, 0);
        assert_eq!(initial_ports, vec![8000]);

        let clamped_ports = candidate_ports(8000, 100);
        assert_eq!(clamped_ports.len(), 50);
        assert_eq!(clamped_ports[0], 8000);
        assert_eq!(clamped_ports[49], 8049);
    }

    #[test]
    fn first_available_port_skips_conflicts() {
        let port = first_available_port(&[8000, 8001, 8002], |candidate| candidate == 8002);

        assert_eq!(port, Some(8002));
    }

    #[test]
    fn initialization_script_injects_backend_url_and_diagnostics() {
        let diagnostics = RuntimeDiagnostics::new(
            RuntimeMode::Dev,
            "http://127.0.0.1:5173".to_string(),
            "D:/app/backend".to_string(),
            "D:/app/data".to_string(),
            "127.0.0.1".to_string(),
            8000,
            15_000,
        );

        let script = build_initialization_script("http://127.0.0.1:8002", &diagnostics);

        assert!(script.contains("window.__LMCA_BACKEND_URL__"));
        assert!(script.contains("http://127.0.0.1:8002"));
        assert!(script.contains("window.fetch ="));
    }

    #[test]
    fn backend_environment_includes_runtime_layout_vars() {
        let config = RuntimeConfig {
            frontend_url: "app://index.html".to_string(),
            backend_root: PathBuf::from("D:/bundle/resources/backend"),
            python_command: "D:/bundle/resources/python/python.exe".to_string(),
            backend_host: "127.0.0.1".to_string(),
            preferred_port: 8000,
            fallback_attempts: 5,
            health_timeout: Duration::from_secs(15),
            poll_interval: Duration::from_millis(250),
            runtime_mode: RuntimeMode::Bundled,
            app_data_dir: PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable"),
            database_url:
                "sqlite:///C:/Users/alice/AppData/Local/AIMemoryCard/stable/data/ai_memory_card.db"
                    .to_string(),
            log_dir: PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable/logs"),
            cache_dir: PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable/cache"),
            plugin_root: PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable/plugins"),
        };

        let env_vars = config.backend_environment(8002);

        assert_eq!(env_vars.get("LMCA_BACKEND_PORT"), Some(&"8002".to_string()));
        assert_eq!(
            env_vars.get("LMCA_RUNTIME_MODE"),
            Some(&"bundled".to_string())
        );
        assert_eq!(
            env_vars.get("LMCA_APP_DATA_DIR"),
            Some(
                &PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable")
                    .display()
                    .to_string()
            )
        );
        assert_eq!(
            env_vars.get("LMCA_DATABASE_URL"),
            Some(
                &"sqlite:///C:/Users/alice/AppData/Local/AIMemoryCard/stable/data/ai_memory_card.db"
                    .to_string()
            )
        );
        assert_eq!(
            env_vars.get("LMCA_LOG_DIR"),
            Some(
                &PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable/logs")
                    .display()
                    .to_string()
            )
        );
        assert_eq!(
            env_vars.get("LMCA_CACHE_DIR"),
            Some(
                &PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable/cache")
                    .display()
                    .to_string()
            )
        );
        assert_eq!(
            env_vars.get("LMCA_PLUGIN_ROOT"),
            Some(
                &PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable/plugins")
                    .display()
                    .to_string()
            )
        );
    }

    #[test]
    fn reap_child_waits_for_already_exited_process() {
        let mut child = exited_child_process();

        let mut status_before_reap = None;
        for _ in 0..20 {
            status_before_reap = child
                .try_wait()
                .expect("try_wait should succeed before reap");
            if status_before_reap.is_some() {
                break;
            }
            sleep(Duration::from_millis(10));
        }
        let status_before_reap = status_before_reap.expect("child should have already exited");
        assert!(status_before_reap.success());

        let reaped_status = reap_child(&mut child).expect("reap should succeed");

        assert!(reaped_status.success());
    }

    fn exited_child_process() -> std::process::Child {
        if cfg!(windows) {
            Command::new("cmd")
                .args(["/C", "exit 0"])
                .spawn()
                .expect("should spawn cmd exit child")
        } else {
            Command::new("sh")
                .args(["-c", "exit 0"])
                .spawn()
                .expect("should spawn shell exit child")
        }
    }
}
