//! Input: 启动阶段事件（端口尝试、进程ID、健康检查等）  |  Output: 诊断快照JSON + 失败HTML页面
//! Role: 桌面层诊断模块，收集并序列化启动过程信息，供失败页面展示和前端注入使用
//! Note: startup_failure_html 生成内联 data: URL 页面，所有用户可见字符串需经 escape_html
//! Usage: 由 runtime.rs 和 main.rs 调用；RuntimeDiagnostics 随启动流程逐步填充状态
use crate::runtime_layout::RuntimeMode;
use serde::Serialize;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum StartupStatus {
    Pending,
    Ready,
    Failed,
}

#[derive(Clone, Debug, Serialize)]
pub struct RuntimeDiagnostics {
    pub startup_started_at_ms: u128,
    pub startup_finished_at_ms: Option<u128>,
    pub status: StartupStatus,
    pub runtime_mode: RuntimeMode,
    pub frontend_url: String,
    pub backend_root: String,
    pub app_data_root: String,
    pub focus_port: Option<u16>,
    pub backend_host: String,
    pub preferred_port: u16,
    pub selected_port: Option<u16>,
    pub attempted_ports: Vec<u16>,
    pub backend_command: Vec<String>,
    pub health_url: Option<String>,
    pub timeout_ms: u64,
    pub health_checks: u32,
    pub child_pid: Option<u32>,
    pub failure_stage: Option<String>,
    pub failure_message: Option<String>,
}

impl RuntimeDiagnostics {
    pub fn new(
        runtime_mode: RuntimeMode,
        frontend_url: String,
        backend_root: String,
        app_data_root: String,
        backend_host: String,
        preferred_port: u16,
        timeout_ms: u64,
    ) -> Self {
        Self {
            startup_started_at_ms: unix_timestamp_ms(),
            startup_finished_at_ms: None,
            status: StartupStatus::Pending,
            runtime_mode,
            frontend_url,
            backend_root,
            app_data_root,
            focus_port: None,
            backend_host,
            preferred_port,
            selected_port: None,
            attempted_ports: Vec::new(),
            backend_command: Vec::new(),
            health_url: None,
            timeout_ms,
            health_checks: 0,
            child_pid: None,
            failure_stage: None,
            failure_message: None,
        }
    }

    pub fn record_port_attempt(&mut self, port: u16) {
        self.attempted_ports.push(port);
    }

    pub fn set_focus_port(&mut self, port: u16) {
        self.focus_port = Some(port);
    }

    pub fn select_port(&mut self, port: u16) {
        self.selected_port = Some(port);
        self.health_url = Some(format!("http://{}:{port}/api/health", self.backend_host));
    }

    pub fn set_backend_command(&mut self, command: Vec<String>) {
        self.backend_command = command;
    }

    pub fn set_child_pid(&mut self, pid: u32) {
        self.child_pid = Some(pid);
    }

    pub fn record_health_check(&mut self) {
        self.health_checks += 1;
    }

    pub fn mark_ready(&mut self) {
        self.status = StartupStatus::Ready;
        self.startup_finished_at_ms = Some(unix_timestamp_ms());
    }

    pub fn mark_failed(&mut self, stage: impl Into<String>, message: impl Into<String>) {
        self.status = StartupStatus::Failed;
        self.failure_stage = Some(stage.into());
        self.failure_message = Some(message.into());
        self.startup_finished_at_ms = Some(unix_timestamp_ms());
    }

    pub fn to_pretty_json(&self) -> String {
        serde_json::to_string_pretty(self)
            .unwrap_or_else(|error| format!("{{\"serialization_error\":\"{error}\"}}"))
    }
}

pub fn friendly_failure_message(diagnostics: &RuntimeDiagnostics) -> String {
    let stage = diagnostics.failure_stage.as_deref().unwrap_or("startup");
    let reason = diagnostics
        .failure_message
        .as_deref()
        .unwrap_or("unknown startup failure");
    let attempted_ports = if diagnostics.attempted_ports.is_empty() {
        "none".to_string()
    } else {
        diagnostics
            .attempted_ports
            .iter()
            .map(u16::to_string)
            .collect::<Vec<_>>()
            .join(", ")
    };

    format!(
        "AI Memory Card could not finish starting.\n\nStage: {stage}\nReason: {reason}\nAttempted ports: {attempted_ports}\nFrontend URL: {}",
        diagnostics.frontend_url
    )
}

pub fn startup_failure_html(user_message: &str, diagnostics: &RuntimeDiagnostics) -> String {
    let diagnostics_json = escape_html(&diagnostics.to_pretty_json());
    let escaped_message = escape_html(user_message);

    format!(
        r#"<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>AI Memory Card Startup Failed</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: "Segoe UI", sans-serif;
        background: #f5efe6;
        color: #1f2933;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: flex;
        align-items: stretch;
        justify-content: center;
        background: radial-gradient(circle at top, #fffaf5 0%, #f5efe6 55%, #eadfd1 100%);
      }}
      main {{
        box-sizing: border-box;
        width: min(900px, 100%);
        padding: 32px 24px 40px;
      }}
      .panel {{
        background: rgba(255, 255, 255, 0.88);
        border: 1px solid #d8c8b3;
        border-radius: 16px;
        box-shadow: 0 18px 48px rgba(77, 58, 36, 0.12);
        padding: 24px;
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: 30px;
      }}
      p {{
        margin: 0 0 16px;
        line-height: 1.5;
      }}
      pre {{
        margin: 0;
        padding: 16px;
        overflow: auto;
        background: #1f2933;
        color: #f6f7f9;
        border-radius: 12px;
        font-size: 13px;
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="panel">
        <h1>Startup failed</h1>
        <p>{escaped_message}</p>
        <pre>{diagnostics_json}</pre>
      </div>
    </main>
  </body>
</html>"#
    )
}

fn unix_timestamp_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default()
}

fn escape_html(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

#[cfg(test)]
mod tests {
    use super::{friendly_failure_message, RuntimeDiagnostics, StartupStatus};
    use crate::runtime_layout::RuntimeMode;

    #[test]
    fn runtime_diagnostics_serializes_core_startup_fields() {
        let mut diagnostics = RuntimeDiagnostics::new(
            RuntimeMode::Dev,
            "http://127.0.0.1:5173".to_string(),
            "D:/app/backend".to_string(),
            "D:/app/data".to_string(),
            "127.0.0.1".to_string(),
            8000,
            15_000,
        );
        diagnostics.record_port_attempt(8000);
        diagnostics.set_focus_port(41001);
        diagnostics.select_port(8001);
        diagnostics.set_backend_command(vec![
            "python".to_string(),
            "-m".to_string(),
            "uvicorn".to_string(),
        ]);
        diagnostics.set_child_pid(4242);
        diagnostics.mark_ready();

        let payload = serde_json::to_value(&diagnostics).expect("diagnostics should serialize");

        assert_eq!(payload["status"], "ready");
        assert_eq!(payload["preferred_port"], 8000);
        assert_eq!(payload["selected_port"], 8001);
        assert_eq!(payload["focus_port"], 41001);
        assert_eq!(payload["child_pid"], 4242);
        assert_eq!(payload["health_url"], "http://127.0.0.1:8001/api/health");
        assert_eq!(payload["runtime_mode"], "dev");
        assert_eq!(payload["app_data_root"], "D:/app/data");
    }

    #[test]
    fn friendly_failure_message_calls_out_stage_and_attempted_ports() {
        let mut diagnostics = RuntimeDiagnostics::new(
            RuntimeMode::Bundled,
            "http://127.0.0.1:5173".to_string(),
            "D:/app/backend".to_string(),
            "D:/app/data".to_string(),
            "127.0.0.1".to_string(),
            8000,
            15_000,
        );
        diagnostics.record_port_attempt(8000);
        diagnostics.record_port_attempt(8001);
        diagnostics.mark_failed("health_timeout", "Timed out waiting for backend health");

        let message = friendly_failure_message(&diagnostics);

        assert_eq!(diagnostics.status, StartupStatus::Failed);
        assert!(message.contains("health_timeout"));
        assert!(message.contains("8000, 8001"));
        assert!(message.contains("Timed out waiting for backend health"));
    }
}
