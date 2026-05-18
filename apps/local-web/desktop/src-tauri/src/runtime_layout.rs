// Input: dev/bundled ???????????????  |  Output: ???? Python?backend?logs?cache ???
// Output: ?????????????????????????????
// Role: ?? desktop runtime ???????????
// Use: ?? release ????????????????? prepare-release ? package-portable
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeMode {
    Dev,
    Bundled,
}

impl RuntimeMode {
    pub fn as_env_value(self) -> &'static str {
        match self {
            Self::Dev => "dev",
            Self::Bundled => "bundled",
        }
    }

    fn app_data_suffix(self) -> &'static str {
        match self {
            Self::Dev => "dev",
            Self::Bundled => "stable",
        }
    }

    fn from_override(value: &str) -> Option<Self> {
        if value.eq_ignore_ascii_case("dev") {
            Some(Self::Dev)
        } else if value.eq_ignore_ascii_case("bundled") {
            Some(Self::Bundled)
        } else {
            None
        }
    }
}

#[derive(Clone, Debug)]
pub struct RuntimeLayoutInputs {
    pub debug_assertions: bool,
    pub repo_backend_root: PathBuf,
    pub local_data_dir: Option<PathBuf>,
    pub resource_dir: Option<PathBuf>,
    pub backend_root_override: Option<PathBuf>,
    pub python_command_override: Option<String>,
    pub runtime_mode_override: Option<String>,
    pub data_config_root: Option<PathBuf>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResolvedRuntimeLayout {
    pub runtime_mode: RuntimeMode,
    pub backend_root: PathBuf,
    pub python_command: String,
    pub app_data_root: PathBuf,
    pub database_url: String,
    pub log_dir: PathBuf,
    pub cache_dir: PathBuf,
    pub plugin_root: PathBuf,
}

pub fn resolve_runtime_layout(
    inputs: RuntimeLayoutInputs,
) -> Result<ResolvedRuntimeLayout, String> {
    let runtime_mode = resolve_runtime_mode(
        inputs.debug_assertions,
        inputs.runtime_mode_override.as_deref(),
    )?;
    let local_data_dir = inputs.local_data_dir.ok_or_else(|| {
        "Unable to determine the OS local data directory for runtime storage".to_string()
    })?;
    let default_app_data_root =
        app_data_root_for_mode(runtime_mode, Some(local_data_dir.as_path()))
            .expect("local data dir should resolve app data root");
    let data_config_root = inputs
        .data_config_root
        .unwrap_or_else(|| local_data_dir.join("AIMemoryCard"));
    let data_state = crate::data_directory::read_data_directory_state(
        runtime_mode,
        &data_config_root,
        &default_app_data_root,
    )?;
    let app_data_root = data_state.current_app_data_root;
    let resource_dir = inputs.resource_dir;
    let backend_root = match inputs.backend_root_override {
        Some(path) => path,
        None => match runtime_mode {
            RuntimeMode::Dev => inputs.repo_backend_root,
            RuntimeMode::Bundled => resource_dir
                .clone()
                .ok_or_else(|| "Bundled runtime requires a Tauri resource directory".to_string())?
                .join("backend"),
        },
    };
    let python_command = match inputs.python_command_override {
        Some(command) => command,
        None => match runtime_mode {
            RuntimeMode::Dev => "python".to_string(),
            RuntimeMode::Bundled => normalized_path_string(
                &resource_dir
                    .ok_or_else(|| {
                        "Bundled runtime requires a Tauri resource directory".to_string()
                    })?
                    .join(bundled_python_relative_path_for(std::env::consts::OS)),
            ),
        },
    };
    let database_path = app_data_root.join("data").join("ai_memory_card.db");

    Ok(ResolvedRuntimeLayout {
        runtime_mode,
        plugin_root: backend_root
            .parent()
            .unwrap_or_else(|| Path::new(""))
            .join("plugins"),
        backend_root,
        python_command,
        app_data_root: app_data_root.clone(),
        database_url: sqlite_database_url(&database_path),
        log_dir: app_data_root.join("logs"),
        cache_dir: app_data_root.join("cache"),
    })
}

pub fn resolve_runtime_mode(
    debug_assertions: bool,
    runtime_mode_override: Option<&str>,
) -> Result<RuntimeMode, String> {
    if let Some(value) = runtime_mode_override {
        return RuntimeMode::from_override(value).ok_or_else(|| {
            format!("Unsupported LMCA_RUNTIME_MODE value '{value}'. Expected 'dev' or 'bundled'.")
        });
    }

    Ok(if debug_assertions {
        RuntimeMode::Dev
    } else {
        RuntimeMode::Bundled
    })
}

pub fn app_data_root_for_mode(
    runtime_mode: RuntimeMode,
    local_data_dir: Option<&Path>,
) -> Option<PathBuf> {
    local_data_dir.map(|path| {
        path.join("AIMemoryCard")
            .join(runtime_mode.app_data_suffix())
    })
}

fn sqlite_database_url(path: &Path) -> String {
    format!("sqlite:///{}", normalized_path_string(path))
}

fn normalized_path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn bundled_python_relative_path_for(target_os: &str) -> PathBuf {
    let executable_name = if target_os.eq_ignore_ascii_case("windows") {
        "pythonw.exe"
    } else {
        "python"
    };

    PathBuf::from("python").join(executable_name)
}

#[cfg(test)]
mod tests {
    use super::{
        bundled_python_relative_path_for, resolve_runtime_layout, RuntimeLayoutInputs, RuntimeMode,
    };
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn base_inputs() -> RuntimeLayoutInputs {
        RuntimeLayoutInputs {
            debug_assertions: false,
            repo_backend_root: PathBuf::from("D:/repo/apps/local-web/backend"),
            local_data_dir: Some(PathBuf::from("C:/Users/alice/AppData/Local")),
            resource_dir: Some(PathBuf::from("D:/bundle/resources")),
            backend_root_override: None,
            python_command_override: None,
            runtime_mode_override: None,
            data_config_root: None,
        }
    }

    fn unique_temp_dir(label: &str) -> PathBuf {
        let id = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!(
            "lmca-runtime-layout-{label}-{}-{id}",
            std::process::id()
        ))
    }

    #[test]
    fn resolves_bundled_layout_to_stable_paths_and_embedded_python() {
        let layout = resolve_runtime_layout(base_inputs()).expect("bundled layout should resolve");
        let expected_python_command = PathBuf::from("D:/bundle/resources")
            .join(bundled_python_relative_path_for(std::env::consts::OS))
            .to_string_lossy()
            .replace('\\', "/");

        assert_eq!(layout.runtime_mode, RuntimeMode::Bundled);
        assert_eq!(
            layout.backend_root,
            PathBuf::from("D:/bundle/resources/backend")
        );
        assert_eq!(layout.python_command, expected_python_command);
        assert_eq!(
            layout.app_data_root,
            PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable")
        );
        assert_eq!(
            layout.database_url,
            "sqlite:///C:/Users/alice/AppData/Local/AIMemoryCard/stable/data/ai_memory_card.db"
        );
        assert_eq!(
            layout.log_dir,
            PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable/logs")
        );
        assert_eq!(
            layout.cache_dir,
            PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/stable/cache")
        );
        assert_eq!(layout.plugin_root, PathBuf::from("D:/bundle/resources/plugins"));
    }

    #[test]
    fn bundled_layout_uses_custom_app_data_root_from_config() {
        let config_root = unique_temp_dir("layout-config");
        let custom_root = unique_temp_dir("layout-custom");
        fs::create_dir_all(&config_root).expect("config root should create");
        let config = crate::data_directory::RuntimeDataDirectoryConfig {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            custom_app_data_root: Some(custom_root.clone()),
            default_location_confirmed_at: None,
            migration_completed_at: Some("2026-04-24T10:00:00Z".to_string()),
        };
        fs::write(
            crate::data_directory::runtime_config_path(&config_root, RuntimeMode::Bundled),
            serde_json::to_vec(&config).expect("config should serialize"),
        )
        .expect("config should write");

        let layout = resolve_runtime_layout(RuntimeLayoutInputs {
            data_config_root: Some(config_root.clone()),
            ..base_inputs()
        })
        .expect("layout should resolve");

        assert_eq!(layout.app_data_root, custom_root);
        assert!(layout.database_url.ends_with("/data/ai_memory_card.db"));

        let _ = fs::remove_dir_all(config_root);
    }

    #[test]
    fn runtime_mode_override_forces_bundled_layout_in_debug() {
        let layout = resolve_runtime_layout(RuntimeLayoutInputs {
            debug_assertions: true,
            runtime_mode_override: Some("bundled".to_string()),
            ..base_inputs()
        })
        .expect("runtime mode override should resolve");

        assert_eq!(layout.runtime_mode, RuntimeMode::Bundled);
        assert_eq!(
            layout.backend_root,
            PathBuf::from("D:/bundle/resources/backend")
        );
    }

    #[test]
    fn resolves_dev_layout_defaults_to_repo_backend_and_dev_app_data() {
        let layout = resolve_runtime_layout(RuntimeLayoutInputs {
            debug_assertions: true,
            resource_dir: None,
            runtime_mode_override: None,
            ..base_inputs()
        })
        .expect("dev layout should resolve");

        assert_eq!(layout.runtime_mode, RuntimeMode::Dev);
        assert_eq!(
            layout.backend_root,
            PathBuf::from("D:/repo/apps/local-web/backend")
        );
        assert_eq!(layout.plugin_root, PathBuf::from("D:/repo/apps/local-web/plugins"));
        assert_eq!(layout.python_command, "python".to_string());
        assert_eq!(
            layout.app_data_root,
            PathBuf::from("C:/Users/alice/AppData/Local/AIMemoryCard/dev")
        );
    }

    #[test]
    fn dev_layout_respects_backend_and_python_overrides() {
        let layout = resolve_runtime_layout(RuntimeLayoutInputs {
            debug_assertions: true,
            backend_root_override: Some(PathBuf::from("E:/custom/backend")),
            python_command_override: Some("E:/python/python.exe".to_string()),
            resource_dir: None,
            ..base_inputs()
        })
        .expect("overrides should resolve");

        assert_eq!(layout.runtime_mode, RuntimeMode::Dev);
        assert_eq!(layout.backend_root, PathBuf::from("E:/custom/backend"));
        assert_eq!(layout.plugin_root, PathBuf::from("E:/custom/plugins"));
        assert_eq!(layout.python_command, "E:/python/python.exe".to_string());
    }

    #[test]
    fn bundled_python_relative_path_is_platform_aware() {
        assert_eq!(
            bundled_python_relative_path_for("windows"),
            PathBuf::from("python").join("pythonw.exe")
        );
        assert_eq!(
            bundled_python_relative_path_for("linux"),
            PathBuf::from("python").join("python")
        );
        assert_eq!(
            bundled_python_relative_path_for("macos"),
            PathBuf::from("python").join("python")
        );
    }
}
