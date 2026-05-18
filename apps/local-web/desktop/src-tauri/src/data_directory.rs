use crate::runtime_layout::RuntimeMode;
use serde::{Deserialize, Serialize};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

const STAGING_MARKER_FILENAME: &str = ".lmca-staging-marker";

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct DataDirectoryState {
    pub runtime_mode: RuntimeMode,
    pub current_app_data_root: PathBuf,
    pub default_app_data_root: PathBuf,
    pub custom_app_data_root: Option<PathBuf>,
    pub migration_allowed: bool,
    pub pending_target_app_data_root: Option<PathBuf>,
    pub desktop_bridge_available: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeDataDirectoryConfig {
    pub schema_version: u8,
    pub runtime_mode: RuntimeMode,
    pub custom_app_data_root: Option<PathBuf>,
    pub default_location_confirmed_at: Option<String>,
    pub migration_completed_at: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct PendingDataMigration {
    pub schema_version: u8,
    pub runtime_mode: RuntimeMode,
    pub source_app_data_root: PathBuf,
    pub target_app_data_root: PathBuf,
    pub created_at: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
struct StagingMarker {
    schema_version: u8,
    target_app_data_root: PathBuf,
}

pub fn runtime_config_filename(runtime_mode: RuntimeMode) -> &'static str {
    match runtime_mode {
        RuntimeMode::Dev => "runtime-config.dev.json",
        RuntimeMode::Bundled => "runtime-config.stable.json",
    }
}

pub fn pending_migration_filename(runtime_mode: RuntimeMode) -> &'static str {
    match runtime_mode {
        RuntimeMode::Dev => "pending-data-migration.dev.json",
        RuntimeMode::Bundled => "pending-data-migration.stable.json",
    }
}

pub fn runtime_config_path(config_root: &Path, runtime_mode: RuntimeMode) -> PathBuf {
    config_root.join(runtime_config_filename(runtime_mode))
}

pub fn pending_migration_path(config_root: &Path, runtime_mode: RuntimeMode) -> PathBuf {
    config_root.join(pending_migration_filename(runtime_mode))
}

pub fn read_data_directory_state(
    runtime_mode: RuntimeMode,
    config_root: &Path,
    default_app_data_root: &Path,
) -> Result<DataDirectoryState, String> {
    let config = read_runtime_config(config_root, runtime_mode)?;
    let pending = read_pending_migration(config_root, runtime_mode)?;
    let custom_app_data_root = config
        .as_ref()
        .and_then(|value| value.custom_app_data_root.clone());
    let current_app_data_root = custom_app_data_root
        .clone()
        .unwrap_or_else(|| default_app_data_root.to_path_buf());
    let pending_target_app_data_root = pending.map(|value| value.target_app_data_root);
    let migration_allowed = pending_target_app_data_root.is_none();

    Ok(DataDirectoryState {
        runtime_mode,
        current_app_data_root,
        default_app_data_root: default_app_data_root.to_path_buf(),
        custom_app_data_root,
        migration_allowed,
        pending_target_app_data_root,
        desktop_bridge_available: true,
    })
}

pub fn read_runtime_config(
    config_root: &Path,
    runtime_mode: RuntimeMode,
) -> Result<Option<RuntimeDataDirectoryConfig>, String> {
    let path = runtime_config_path(config_root, runtime_mode);
    let payload = match fs::read(&path) {
        Ok(payload) => payload,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(format!("Failed to read {}: {error}", path.display())),
    };
    let config: RuntimeDataDirectoryConfig = serde_json::from_slice(&payload)
        .map_err(|error| format!("Failed to parse {}: {error}", path.display()))?;
    if config.schema_version != 1 {
        return Err(format!(
            "Unsupported data directory config schema version {}",
            config.schema_version
        ));
    }
    if config.runtime_mode != runtime_mode {
        return Err(format!(
            "Data directory config mode mismatch: expected {:?}, got {:?}",
            runtime_mode, config.runtime_mode
        ));
    }
    Ok(Some(config))
}

pub fn read_pending_migration(
    config_root: &Path,
    runtime_mode: RuntimeMode,
) -> Result<Option<PendingDataMigration>, String> {
    let path = pending_migration_path(config_root, runtime_mode);
    let payload = match fs::read(&path) {
        Ok(payload) => payload,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(format!("Failed to read {}: {error}", path.display())),
    };
    let migration: PendingDataMigration = serde_json::from_slice(&payload)
        .map_err(|error| format!("Failed to parse {}: {error}", path.display()))?;
    if migration.schema_version != 1 {
        return Err(format!(
            "Unsupported pending migration schema version {}",
            migration.schema_version
        ));
    }
    if migration.runtime_mode != runtime_mode {
        return Err(format!(
            "Pending migration mode mismatch: expected {:?}, got {:?}",
            runtime_mode, migration.runtime_mode
        ));
    }
    Ok(Some(migration))
}

pub fn write_runtime_config(
    config_root: &Path,
    config: &RuntimeDataDirectoryConfig,
) -> Result<(), String> {
    fs::create_dir_all(config_root).map_err(|error| {
        format!(
            "Failed to create config root {}: {error}",
            config_root.display()
        )
    })?;
    let path = runtime_config_path(config_root, config.runtime_mode);
    let payload = serde_json::to_vec_pretty(config)
        .map_err(|error| format!("Failed to serialize data directory config: {error}"))?;
    let (temp_path, mut temp_file) =
        create_runtime_config_temp_file(config_root, config.runtime_mode)?;
    let write_result = temp_file
        .write_all(&payload)
        .and_then(|()| temp_file.sync_all());
    drop(temp_file);
    if let Err(error) = write_result {
        cleanup_runtime_config_temp_file(&temp_path);
        return Err(format!(
            "Failed to write runtime config temp file {}: {error}",
            temp_path.display()
        ));
    }
    match fs::rename(&temp_path, &path) {
        Ok(()) => Ok(()),
        Err(error) => {
            cleanup_runtime_config_temp_file(&temp_path);
            Err(format!(
                "Failed to publish runtime config {}: {error}",
                path.display()
            ))
        }
    }
}

pub fn write_pending_migration_if_absent(
    config_root: &Path,
    runtime_mode: RuntimeMode,
    pending: &PendingDataMigration,
) -> Result<(), String> {
    if pending.runtime_mode != runtime_mode {
        return Err(format!(
            "Pending migration mode mismatch: expected {:?}, got {:?}",
            runtime_mode, pending.runtime_mode
        ));
    }
    fs::create_dir_all(config_root).map_err(|error| {
        format!(
            "Failed to create config root {}: {error}",
            config_root.display()
        )
    })?;
    let path = pending_migration_path(config_root, runtime_mode);
    let payload = serde_json::to_vec_pretty(pending)
        .map_err(|error| format!("Failed to serialize pending migration: {error}"))?;
    let (temp_path, mut temp_file) = create_pending_temp_file(config_root, runtime_mode)?;
    let write_result = temp_file
        .write_all(&payload)
        .and_then(|()| temp_file.sync_all());
    drop(temp_file);
    if let Err(error) = write_result {
        cleanup_pending_temp_file(&temp_path);
        return Err(format!(
            "Failed to write pending migration temp file {}: {error}",
            temp_path.display()
        ));
    }

    match fs::hard_link(&temp_path, &path) {
        Ok(()) => {
            fs::remove_file(&temp_path).map_err(|error| {
                format!(
                    "Pending migration was written, but failed to remove temp file {}: {error}",
                    temp_path.display()
                )
            })?;
            Ok(())
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            cleanup_pending_temp_file(&temp_path);
            Err(format!(
                "Data directory migration is already scheduled at {}",
                path.display()
            ))
        }
        Err(error) => {
            cleanup_pending_temp_file(&temp_path);
            Err(format!(
                "Failed to publish pending migration {}: {error}",
                path.display()
            ))
        }
    }
}

pub fn apply_pending_migration(
    runtime_mode: RuntimeMode,
    config_root: &Path,
    resource_root: Option<&Path>,
) -> Result<bool, String> {
    let pending = match read_pending_migration(config_root, runtime_mode)? {
        Some(pending) => pending,
        None => return Ok(false),
    };

    if target_appears_activated(&pending.target_app_data_root) {
        write_completed_migration_config(runtime_mode, config_root, &pending.target_app_data_root)?;
        remove_pending_migration_file(config_root, runtime_mode)?;
        return Ok(true);
    }

    if runtime_config_points_to_target(config_root, runtime_mode, &pending.target_app_data_root)? {
        remove_pending_migration_file(config_root, runtime_mode)?;
        return Ok(true);
    }

    validate_migration_target(
        &pending.source_app_data_root,
        &pending.target_app_data_root,
        resource_root,
    )?;
    copy_durable_data(&pending.source_app_data_root, &pending.target_app_data_root)?;

    write_completed_migration_config(runtime_mode, config_root, &pending.target_app_data_root)?;
    remove_pending_migration_file(config_root, runtime_mode)?;
    Ok(true)
}

pub fn schedule_data_directory_migration(
    runtime_mode: RuntimeMode,
    config_root: &Path,
    default_app_data_root: &Path,
    current_app_data_root: &Path,
    resource_root: Option<&Path>,
    target_app_data_root: &Path,
) -> Result<DataDirectoryState, String> {
    let current_state =
        read_data_directory_state(runtime_mode, config_root, default_app_data_root)?;
    if !current_state.migration_allowed {
        return Err("Data directory migration is already configured".to_string());
    }

    validate_migration_target(current_app_data_root, target_app_data_root, resource_root)?;
    fs::create_dir_all(config_root).map_err(|error| {
        format!(
            "Failed to create config root {}: {error}",
            config_root.display()
        )
    })?;
    let pending = PendingDataMigration {
        schema_version: 1,
        runtime_mode,
        source_app_data_root: current_app_data_root.to_path_buf(),
        target_app_data_root: target_app_data_root.to_path_buf(),
        created_at: now_utc_string(),
    };
    write_pending_migration_if_absent(config_root, runtime_mode, &pending)?;
    read_data_directory_state(runtime_mode, config_root, default_app_data_root)
}

#[tauri::command]
pub fn lmca_get_data_directory_state(
    state: tauri::State<'_, crate::DataDirectoryCommandState>,
) -> Result<DataDirectoryState, String> {
    read_data_directory_state(
        state.runtime_mode,
        &state.config_root,
        &state.default_app_data_root,
    )
}

#[tauri::command]
pub fn lmca_choose_data_directory() -> Result<Option<PathBuf>, String> {
    Ok(tauri::api::dialog::blocking::FileDialogBuilder::new().pick_folder())
}

#[tauri::command]
pub fn lmca_schedule_data_directory_migration(
    state: tauri::State<'_, crate::DataDirectoryCommandState>,
    target_app_data_root: PathBuf,
) -> Result<DataDirectoryState, String> {
    schedule_data_directory_migration(
        state.runtime_mode,
        &state.config_root,
        &state.default_app_data_root,
        &state.current_app_data_root,
        state.resource_root.as_deref(),
        &target_app_data_root,
    )
}

pub fn validate_migration_target(
    current_app_data_root: &Path,
    target_app_data_root: &Path,
    resource_root: Option<&Path>,
) -> Result<(), String> {
    if !target_app_data_root.is_absolute() {
        return Err("Data directory must be an absolute path".to_string());
    }
    if paths_equal(current_app_data_root, target_app_data_root) {
        return Err("Target directory is the same as the current data directory".to_string());
    }
    if path_is_same_or_child(target_app_data_root, current_app_data_root) {
        return Err("Target directory cannot be inside the current data directory".to_string());
    }
    if let Some(resource_root) = resource_root {
        if path_is_same_or_child(target_app_data_root, resource_root) {
            return Err("Target directory cannot be inside the application resources".to_string());
        }
    }
    if target_app_data_root.is_file() {
        return Err("Target data directory points to a file".to_string());
    }
    fs::create_dir_all(target_app_data_root)
        .map_err(|error| format!("Failed to create target directory: {error}"))?;
    let probe_path = target_app_data_root.join(".lmca-write-test");
    fs::write(&probe_path, b"ok")
        .map_err(|error| format!("Target directory is not writable: {error}"))?;
    let _ = fs::remove_file(&probe_path);
    if target_app_data_root
        .join("data")
        .join("ai_memory_card.db")
        .exists()
    {
        return Err("Target directory already contains an AI Memory Card database".to_string());
    }
    if directory_has_entries(target_app_data_root)? {
        return Err("Target directory must be empty before migration".to_string());
    }
    Ok(())
}

pub fn copy_durable_data(source_root: &Path, target_root: &Path) -> Result<(), String> {
    if target_root.exists() && directory_has_entries(target_root)? {
        return Err("Target directory must be empty before migration".to_string());
    }

    let staging_root = staging_root_for(target_root);
    if staging_root.exists() {
        remove_owned_staging_root(&staging_root, target_root)?;
    }
    fs::create_dir_all(&staging_root).map_err(|error| {
        format!(
            "Failed to create staging root {}: {error}",
            staging_root.display()
        )
    })?;
    write_staging_marker(&staging_root, target_root)?;
    copy_dir_if_exists(&source_root.join("data"), &staging_root.join("data"))?;
    copy_dir_if_exists(&source_root.join("backups"), &staging_root.join("backups"))?;
    fs::create_dir_all(staging_root.join("logs"))
        .map_err(|error| format!("Failed to create logs directory: {error}"))?;
    fs::create_dir_all(staging_root.join("cache"))
        .map_err(|error| format!("Failed to create cache directory: {error}"))?;
    fs::create_dir_all(staging_root.join("temp"))
        .map_err(|error| format!("Failed to create temp directory: {error}"))?;
    activate_staged_migration(&staging_root, target_root)?;
    Ok(())
}

fn activate_staged_migration(staging_root: &Path, target_root: &Path) -> Result<(), String> {
    if target_root.exists() {
        if directory_has_entries(target_root)? {
            return Err("Target directory must be empty before activation".to_string());
        }
        fs::remove_dir(target_root)
            .map_err(|error| format!("Failed to clear empty target directory: {error}"))?;
    }
    remove_file_if_exists(&staging_marker_path(staging_root))?;
    fs::rename(&staging_root, target_root).map_err(|error| {
        format!(
            "Failed to activate migrated data directory {}: {error}",
            target_root.display()
        )
    })?;
    Ok(())
}

fn runtime_config_points_to_target(
    config_root: &Path,
    runtime_mode: RuntimeMode,
    target_root: &Path,
) -> Result<bool, String> {
    let config = match read_runtime_config(config_root, runtime_mode)? {
        Some(config) => config,
        None => return Ok(false),
    };
    Ok(config
        .custom_app_data_root
        .as_ref()
        .is_some_and(|configured_root| paths_equal(configured_root, target_root)))
}

fn target_appears_activated(target_root: &Path) -> bool {
    target_root
        .join("data")
        .join("ai_memory_card.db")
        .is_file()
}

fn write_completed_migration_config(
    runtime_mode: RuntimeMode,
    config_root: &Path,
    target_root: &Path,
) -> Result<(), String> {
    let config = RuntimeDataDirectoryConfig {
        schema_version: 1,
        runtime_mode,
        custom_app_data_root: Some(target_root.to_path_buf()),
        default_location_confirmed_at: None,
        migration_completed_at: Some(now_utc_string()),
    };
    write_runtime_config(config_root, &config)
}

fn remove_pending_migration_file(
    config_root: &Path,
    runtime_mode: RuntimeMode,
) -> Result<(), String> {
    let path = pending_migration_path(config_root, runtime_mode);
    match fs::remove_file(&path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!(
            "Failed to remove pending migration file {}: {error}",
            path.display()
        )),
    }
}

fn create_runtime_config_temp_file(
    config_root: &Path,
    runtime_mode: RuntimeMode,
) -> Result<(PathBuf, File), String> {
    for attempt in 0..10 {
        let temp_path = runtime_config_temp_path(config_root, runtime_mode, attempt);
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp_path)
        {
            Ok(file) => return Ok((temp_path, file)),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(format!(
                    "Failed to create runtime config temp file {}: {error}",
                    temp_path.display()
                ))
            }
        }
    }
    Err("Failed to create a unique runtime config temp file".to_string())
}

fn runtime_config_temp_path(config_root: &Path, runtime_mode: RuntimeMode, attempt: u8) -> PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    config_root.join(format!(
        ".{}.{}.{}.{}.tmp",
        runtime_config_filename(runtime_mode),
        std::process::id(),
        nanos,
        attempt
    ))
}

fn cleanup_runtime_config_temp_file(path: &Path) {
    let _ = fs::remove_file(path);
}

fn create_pending_temp_file(
    config_root: &Path,
    runtime_mode: RuntimeMode,
) -> Result<(PathBuf, File), String> {
    for attempt in 0..10 {
        let temp_path = pending_migration_temp_path(config_root, runtime_mode, attempt);
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp_path)
        {
            Ok(file) => return Ok((temp_path, file)),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(format!(
                    "Failed to create pending migration temp file {}: {error}",
                    temp_path.display()
                ))
            }
        }
    }
    Err("Failed to create a unique pending migration temp file".to_string())
}

fn pending_migration_temp_path(
    config_root: &Path,
    runtime_mode: RuntimeMode,
    attempt: u8,
) -> PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    config_root.join(format!(
        ".{}.{}.{}.{}.tmp",
        pending_migration_filename(runtime_mode),
        std::process::id(),
        nanos,
        attempt
    ))
}

fn cleanup_pending_temp_file(path: &Path) {
    let _ = fs::remove_file(path);
}

fn staging_root_for(target_root: &Path) -> PathBuf {
    let parent = target_root.parent().unwrap_or_else(|| Path::new("."));
    let name = target_root
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("data-root");
    parent.join(format!(".lmca-migration-{name}"))
}

fn staging_marker_path(staging_root: &Path) -> PathBuf {
    staging_root.join(STAGING_MARKER_FILENAME)
}

fn write_staging_marker(staging_root: &Path, target_root: &Path) -> Result<(), String> {
    let marker = StagingMarker {
        schema_version: 1,
        target_app_data_root: comparable_path(target_root),
    };
    let payload = serde_json::to_vec_pretty(&marker)
        .map_err(|error| format!("Failed to serialize staging marker: {error}"))?;
    fs::write(staging_marker_path(staging_root), payload)
        .map_err(|error| format!("Failed to write staging marker: {error}"))
}

fn remove_owned_staging_root(staging_root: &Path, target_root: &Path) -> Result<(), String> {
    let marker = read_staging_marker(staging_root)?;
    if marker.schema_version != 1 || !paths_equal(&marker.target_app_data_root, target_root) {
        return Err(format!(
            "Refusing to remove staging directory {} because its marker does not match the target",
            staging_root.display()
        ));
    }
    fs::remove_dir_all(staging_root).map_err(|error| {
        format!(
            "Failed to remove stale staging directory {}: {error}",
            staging_root.display()
        )
    })
}

fn read_staging_marker(staging_root: &Path) -> Result<StagingMarker, String> {
    let path = staging_marker_path(staging_root);
    let payload = fs::read(&path).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            format!(
                "Refusing to remove unmarked staging directory {}",
                staging_root.display()
            )
        } else {
            format!("Failed to read staging marker {}: {error}", path.display())
        }
    })?;
    serde_json::from_slice(&payload)
        .map_err(|error| format!("Failed to parse staging marker {}: {error}", path.display()))
}

fn directory_has_entries(path: &Path) -> Result<bool, String> {
    Ok(fs::read_dir(path)
        .map_err(|error| {
            format!(
                "Failed to inspect target directory {}: {error}",
                path.display()
            )
        })?
        .next()
        .is_some())
}

fn copy_dir_if_exists(source: &Path, target: &Path) -> Result<(), String> {
    if !source.exists() {
        fs::create_dir_all(target)
            .map_err(|error| format!("Failed to create {}: {error}", target.display()))?;
        return Ok(());
    }
    fs::create_dir_all(target)
        .map_err(|error| format!("Failed to create {}: {error}", target.display()))?;
    for entry in fs::read_dir(source)
        .map_err(|error| format!("Failed to read {}: {error}", source.display()))?
    {
        let entry = entry.map_err(|error| format!("Failed to read directory entry: {error}"))?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if source_path.is_dir() {
            copy_dir_if_exists(&source_path, &target_path)?;
        } else {
            fs::copy(&source_path, &target_path).map_err(|error| {
                format!(
                    "Failed to copy {} to {}: {error}",
                    source_path.display(),
                    target_path.display()
                )
            })?;
        }
    }
    Ok(())
}

fn remove_file_if_exists(path: &Path) -> Result<(), String> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("Failed to remove {}: {error}", path.display())),
    }
}

fn paths_equal(left: &Path, right: &Path) -> bool {
    comparable_path(left) == comparable_path(right)
}

fn path_is_same_or_child(path: &Path, root: &Path) -> bool {
    comparable_path(path).starts_with(comparable_path(root))
}

fn comparable_path(path: &Path) -> PathBuf {
    if let Ok(canonical) = path.canonicalize() {
        return canonical;
    }
    let mut cursor = path;
    while let Some(parent) = cursor.parent() {
        if let Ok(canonical_parent) = parent.canonicalize() {
            let suffix = path.strip_prefix(parent).unwrap_or_else(|_| Path::new(""));
            return canonical_parent.join(suffix);
        }
        cursor = parent;
    }
    path.to_path_buf()
}

fn now_utc_string() -> String {
    let millis = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default();
    format!("unix-ms:{millis}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_filenames_are_mode_scoped() {
        assert_eq!(
            runtime_config_filename(RuntimeMode::Dev),
            "runtime-config.dev.json"
        );
        assert_eq!(
            runtime_config_filename(RuntimeMode::Bundled),
            "runtime-config.stable.json"
        );
        assert_eq!(
            pending_migration_filename(RuntimeMode::Dev),
            "pending-data-migration.dev.json"
        );
        assert_eq!(
            pending_migration_filename(RuntimeMode::Bundled),
            "pending-data-migration.stable.json"
        );
    }

    #[test]
    fn state_uses_default_root_when_no_config_exists() {
        let config_root = unique_temp_dir("state-default-config");
        let default_root = unique_temp_dir("state-default-data");

        let state = read_data_directory_state(RuntimeMode::Bundled, &config_root, &default_root)
            .expect("state should load without config");

        assert_eq!(state.current_app_data_root, default_root);
        assert_eq!(state.default_app_data_root, default_root);
        assert_eq!(state.custom_app_data_root, None);
        assert_eq!(state.pending_target_app_data_root, None);
        assert!(state.migration_allowed);
        assert!(state.desktop_bridge_available);

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&default_root);
    }

    #[test]
    fn state_disallows_new_migration_when_pending_migration_exists() {
        let config_root = unique_temp_dir("state-pending-config");
        let default_root = unique_temp_dir("state-pending-data");
        let target_root = unique_temp_dir("state-pending-target");
        fs::create_dir_all(&config_root).expect("config root should exist");
        let migration = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: default_root.clone(),
            target_app_data_root: target_root.clone(),
            created_at: "2026-04-24T00:00:00Z".to_string(),
        };
        fs::write(
            pending_migration_path(&config_root, RuntimeMode::Bundled),
            serde_json::to_vec(&migration).expect("migration should serialize"),
        )
        .expect("pending migration should write");

        let state = read_data_directory_state(RuntimeMode::Bundled, &config_root, &default_root)
            .expect("state should load with pending migration");

        assert_eq!(state.current_app_data_root, default_root);
        assert_eq!(state.pending_target_app_data_root, Some(target_root));
        assert!(!state.migration_allowed);

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&default_root);
    }

    #[test]
    fn state_allows_new_migration_when_custom_root_exists_without_pending_migration() {
        let config_root = unique_temp_dir("state-custom-config");
        let default_root = unique_temp_dir("state-custom-default");
        let custom_root = unique_temp_dir("state-custom-current");
        let config = RuntimeDataDirectoryConfig {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            custom_app_data_root: Some(custom_root.clone()),
            default_location_confirmed_at: None,
            migration_completed_at: Some("unix-ms:already".to_string()),
        };
        write_runtime_config(&config_root, &config).expect("runtime config should write");

        let state = read_data_directory_state(RuntimeMode::Bundled, &config_root, &default_root)
            .expect("state should load with custom directory");

        assert_eq!(state.current_app_data_root, custom_root);
        assert_eq!(state.custom_app_data_root, Some(custom_root.clone()));
        assert_eq!(state.pending_target_app_data_root, None);
        assert!(state.migration_allowed);

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&default_root);
        remove_dir_if_exists(&custom_root);
    }

    #[test]
    fn apply_pending_migration_writes_runtime_config_and_removes_pending_file() {
        let config_root = unique_temp_dir("apply-config");
        let source_root = unique_temp_dir("apply-source");
        let target_root = unique_temp_dir("apply-target");
        fs::create_dir_all(&config_root).expect("config root should create");
        fs::create_dir_all(source_root.join("data")).expect("source data should create");
        fs::write(source_root.join("data").join("ai_memory_card.db"), b"db")
            .expect("db should write");
        let pending = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: source_root.clone(),
            target_app_data_root: target_root.clone(),
            created_at: "2026-04-24T10:00:00Z".to_string(),
        };
        fs::write(
            pending_migration_path(&config_root, RuntimeMode::Bundled),
            serde_json::to_vec(&pending).expect("pending should serialize"),
        )
        .expect("pending should write");

        let applied = apply_pending_migration(
            RuntimeMode::Bundled,
            &config_root,
            Some(Path::new("D:/not-the-target-resource-root")),
        )
        .expect("migration should apply");

        assert!(applied);
        assert!(target_root
            .join("data")
            .join("ai_memory_card.db")
            .is_file());
        assert!(!pending_migration_path(&config_root, RuntimeMode::Bundled).exists());
        let config = read_runtime_config(&config_root, RuntimeMode::Bundled)
            .expect("config should read")
            .expect("config should exist");
        assert_eq!(config.custom_app_data_root, Some(target_root.clone()));
        assert_eq!(config.runtime_mode, RuntimeMode::Bundled);

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&target_root);
    }

    #[test]
    fn apply_pending_migration_clears_pending_when_config_already_points_to_target() {
        let config_root = unique_temp_dir("apply-existing-config");
        let source_root = unique_temp_dir("apply-existing-source");
        let target_root = unique_temp_dir("apply-existing-target");
        fs::create_dir_all(&config_root).expect("config root should create");
        fs::create_dir_all(source_root.join("data")).expect("source data should create");
        fs::create_dir_all(target_root.join("data")).expect("target data should create");
        fs::write(
            source_root.join("data").join("ai_memory_card.db"),
            b"source-db",
        )
        .expect("source db should write");
        fs::write(
            target_root.join("data").join("ai_memory_card.db"),
            b"target-db",
        )
        .expect("target db should write");
        let config = RuntimeDataDirectoryConfig {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            custom_app_data_root: Some(target_root.clone()),
            default_location_confirmed_at: None,
            migration_completed_at: Some("unix-ms:already".to_string()),
        };
        write_runtime_config(&config_root, &config).expect("runtime config should write");
        let pending = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: source_root.clone(),
            target_app_data_root: target_root.clone(),
            created_at: "2026-04-24T10:00:00Z".to_string(),
        };
        fs::write(
            pending_migration_path(&config_root, RuntimeMode::Bundled),
            serde_json::to_vec(&pending).expect("pending should serialize"),
        )
        .expect("pending should write");

        let applied = apply_pending_migration(RuntimeMode::Bundled, &config_root, None)
            .expect("migration recovery should succeed");

        assert!(applied);
        assert!(!pending_migration_path(&config_root, RuntimeMode::Bundled).exists());
        assert_eq!(
            fs::read(target_root.join("data").join("ai_memory_card.db"))
                .expect("target db should remain"),
            b"target-db"
        );

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&target_root);
    }

    #[test]
    fn apply_pending_migration_recovers_activated_target_without_runtime_config() {
        let config_root = unique_temp_dir("apply-activated-config");
        let source_root = unique_temp_dir("apply-activated-source");
        let target_root = unique_temp_dir("apply-activated-target");
        fs::create_dir_all(&config_root).expect("config root should create");
        fs::create_dir_all(source_root.join("data")).expect("source data should create");
        fs::create_dir_all(target_root.join("data")).expect("target data should create");
        fs::write(
            source_root.join("data").join("ai_memory_card.db"),
            b"source-db",
        )
        .expect("source db should write");
        fs::write(
            target_root.join("data").join("ai_memory_card.db"),
            b"target-db",
        )
        .expect("target db should write");
        let pending = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: source_root.clone(),
            target_app_data_root: target_root.clone(),
            created_at: "2026-04-24T10:00:00Z".to_string(),
        };
        fs::write(
            pending_migration_path(&config_root, RuntimeMode::Bundled),
            serde_json::to_vec(&pending).expect("pending should serialize"),
        )
        .expect("pending should write");

        let applied = apply_pending_migration(RuntimeMode::Bundled, &config_root, None)
            .expect("activated target recovery should succeed");

        assert!(applied);
        assert!(!pending_migration_path(&config_root, RuntimeMode::Bundled).exists());
        let config = read_runtime_config(&config_root, RuntimeMode::Bundled)
            .expect("config should read")
            .expect("config should exist");
        assert_eq!(config.custom_app_data_root, Some(target_root.clone()));
        assert_eq!(
            fs::read(target_root.join("data").join("ai_memory_card.db"))
                .expect("target db should remain"),
            b"target-db"
        );

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&target_root);
    }

    #[test]
    fn apply_pending_migration_recovers_activated_target_with_corrupt_runtime_config() {
        let config_root = unique_temp_dir("apply-activated-corrupt-config");
        let source_root = unique_temp_dir("apply-activated-corrupt-source");
        let target_root = unique_temp_dir("apply-activated-corrupt-target");
        fs::create_dir_all(&config_root).expect("config root should create");
        fs::create_dir_all(source_root.join("data")).expect("source data should create");
        fs::create_dir_all(target_root.join("data")).expect("target data should create");
        fs::write(
            source_root.join("data").join("ai_memory_card.db"),
            b"source-db",
        )
        .expect("source db should write");
        fs::write(
            target_root.join("data").join("ai_memory_card.db"),
            b"target-db",
        )
        .expect("target db should write");
        fs::write(
            runtime_config_path(&config_root, RuntimeMode::Bundled),
            b"{ partial config",
        )
        .expect("corrupt runtime config should write");
        let pending = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: source_root.clone(),
            target_app_data_root: target_root.clone(),
            created_at: "2026-04-24T10:00:00Z".to_string(),
        };
        fs::write(
            pending_migration_path(&config_root, RuntimeMode::Bundled),
            serde_json::to_vec(&pending).expect("pending should serialize"),
        )
        .expect("pending should write");

        let applied = apply_pending_migration(RuntimeMode::Bundled, &config_root, None)
            .expect("activated target recovery should repair corrupt config");

        assert!(applied);
        assert!(!pending_migration_path(&config_root, RuntimeMode::Bundled).exists());
        let config = read_runtime_config(&config_root, RuntimeMode::Bundled)
            .expect("config should read")
            .expect("config should exist");
        assert_eq!(config.custom_app_data_root, Some(target_root.clone()));
        assert_eq!(
            fs::read(target_root.join("data").join("ai_memory_card.db"))
                .expect("target db should remain"),
            b"target-db"
        );

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&target_root);
    }

    #[test]
    fn validation_rejects_current_root_and_existing_database() {
        let current_root = unique_temp_dir("validate-current");
        let resource_root = unique_temp_dir("validate-resource");
        let database_target = unique_temp_dir("validate-existing-db");
        fs::create_dir_all(database_target.join("data")).expect("data dir should create");
        fs::write(
            database_target.join("data").join("ai_memory_card.db"),
            b"sqlite",
        )
        .expect("database marker should write");

        let same_root_error =
            validate_migration_target(&current_root, &current_root, Some(&resource_root))
                .expect_err("same root should fail");
        assert!(same_root_error.contains("same as the current data directory"));

        let existing_database_error =
            validate_migration_target(&current_root, &database_target, Some(&resource_root))
                .expect_err("existing database should fail");
        assert!(existing_database_error.contains("already contains an AI Memory Card database"));

        remove_dir_if_exists(&current_root);
        remove_dir_if_exists(&resource_root);
        remove_dir_if_exists(&database_target);
    }

    #[test]
    fn validation_rejects_non_empty_target_without_existing_database() {
        let current_root = unique_temp_dir("validate-non-empty-current");
        let target_root = unique_temp_dir("validate-non-empty-target");
        fs::create_dir_all(&target_root).expect("target should create");
        fs::write(target_root.join("notes.txt"), b"user file").expect("target file should write");

        let error = validate_migration_target(&current_root, &target_root, None)
            .expect_err("non-empty target should fail");

        assert!(error.contains("must be empty"));

        remove_dir_if_exists(&current_root);
        remove_dir_if_exists(&target_root);
    }

    #[test]
    fn activation_rejects_non_empty_target_without_deleting_files() {
        let staging_root = unique_temp_dir("activation-staging");
        let target_root = unique_temp_dir("activation-target");
        fs::create_dir_all(staging_root.join("data")).expect("staging should create");
        fs::write(
            staging_root.join("data").join("ai_memory_card.db"),
            b"db",
        )
        .expect("staged db should write");
        fs::create_dir_all(&target_root).expect("target should create");
        fs::write(target_root.join("late-file.txt"), b"late").expect("late file should write");

        let error = activate_staged_migration(&staging_root, &target_root)
            .expect_err("non-empty target should fail activation");

        assert!(error.contains("Target directory must be empty"));
        assert!(target_root.join("late-file.txt").is_file());
        assert!(staging_root
            .join("data")
            .join("ai_memory_card.db")
            .is_file());

        remove_dir_if_exists(&staging_root);
        remove_dir_if_exists(&target_root);
    }

    #[test]
    fn migration_copy_rejects_unmarked_staging_directory_without_deleting_it() {
        let source_root = unique_temp_dir("copy-unmarked-source");
        let target_root = unique_temp_dir("copy-unmarked-target");
        let stale_staging_root = deterministic_staging_root_for_test(&target_root);
        fs::create_dir_all(source_root.join("data")).expect("source data should create");
        fs::write(source_root.join("data").join("ai_memory_card.db"), b"db")
            .expect("source db should write");
        fs::create_dir_all(&stale_staging_root).expect("stale staging should create");
        fs::write(stale_staging_root.join("partial.tmp"), b"partial")
            .expect("stale file should write");

        let error = copy_durable_data(&source_root, &target_root)
            .expect_err("unmarked staging should be rejected");

        assert!(error.contains("staging"));
        assert!(stale_staging_root.join("partial.tmp").is_file());
        assert!(!target_root.exists());

        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&target_root);
        remove_dir_if_exists(&stale_staging_root);
    }

    #[test]
    fn migration_copy_removes_stale_deterministic_staging_directory() {
        let source_root = unique_temp_dir("copy-stale-source");
        let target_root = unique_temp_dir("copy-stale-target");
        let stale_staging_root = deterministic_staging_root_for_test(&target_root);
        fs::create_dir_all(source_root.join("data")).expect("source data should create");
        fs::write(source_root.join("data").join("ai_memory_card.db"), b"db")
            .expect("source db should write");
        fs::create_dir_all(&stale_staging_root).expect("stale staging should create");
        fs::write(stale_staging_root.join("partial.tmp"), b"partial")
            .expect("stale file should write");
        write_staging_marker(&stale_staging_root, &target_root)
            .expect("stale staging marker should write");

        copy_durable_data(&source_root, &target_root).expect("copy should succeed");

        assert!(target_root
            .join("data")
            .join("ai_memory_card.db")
            .is_file());
        assert!(!stale_staging_root.exists());

        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&target_root);
        remove_dir_if_exists(&stale_staging_root);
    }

    #[test]
    fn migration_copy_includes_data_and_backups_only() {
        let source_root = unique_temp_dir("copy-source");
        let target_root = unique_temp_dir("copy-target");
        fs::create_dir_all(source_root.join("data")).expect("source data should create");
        fs::create_dir_all(source_root.join("backups")).expect("source backups should create");
        fs::create_dir_all(source_root.join("logs")).expect("source logs should create");
        fs::create_dir_all(source_root.join("cache")).expect("source cache should create");
        fs::create_dir_all(source_root.join("temp")).expect("source temp should create");
        fs::write(source_root.join("data").join("ai_memory_card.db"), b"db")
            .expect("db should write");
        fs::write(
            source_root.join("backups").join("snapshot.sqlite3"),
            b"backup",
        )
        .expect("backup should write");
        fs::write(source_root.join("logs").join("app.log"), b"log").expect("log should write");
        fs::write(source_root.join("desktop-instance.lock"), b"lock").expect("lock should write");

        copy_durable_data(&source_root, &target_root).expect("copy should succeed");

        assert!(target_root
            .join("data")
            .join("ai_memory_card.db")
            .is_file());
        assert!(target_root
            .join("backups")
            .join("snapshot.sqlite3")
            .is_file());
        assert!(target_root.join("logs").is_dir());
        assert!(target_root.join("cache").is_dir());
        assert!(target_root.join("temp").is_dir());
        assert!(!target_root.join(STAGING_MARKER_FILENAME).exists());
        assert!(!target_root.join("logs").join("app.log").exists());
        assert!(!target_root.join("desktop-instance.lock").exists());

        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&target_root);
    }

    #[test]
    fn pending_migration_write_if_absent_creates_file_without_temp_leftover() {
        let config_root = unique_temp_dir("pending-write-config");
        let source_root = unique_temp_dir("pending-write-source");
        let target_root = unique_temp_dir("pending-write-target");
        let pending = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: source_root.clone(),
            target_app_data_root: target_root.clone(),
            created_at: "2026-04-24T10:00:00Z".to_string(),
        };

        write_pending_migration_if_absent(&config_root, RuntimeMode::Bundled, &pending)
            .expect("pending migration should write");

        let saved = read_pending_migration(&config_root, RuntimeMode::Bundled)
            .expect("pending migration should read")
            .expect("pending migration should exist");
        assert_eq!(saved, pending);
        assert!(pending_temp_files(&config_root).is_empty());

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&target_root);
    }

    #[test]
    fn pending_migration_write_if_absent_rejects_existing_file_and_preserves_it() {
        let config_root = unique_temp_dir("pending-existing-config");
        let source_root = unique_temp_dir("pending-existing-source");
        let first_target_root = unique_temp_dir("pending-existing-first-target");
        let second_target_root = unique_temp_dir("pending-existing-second-target");
        let existing = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: source_root.clone(),
            target_app_data_root: first_target_root.clone(),
            created_at: "2026-04-24T10:00:00Z".to_string(),
        };
        let attempted = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: source_root.clone(),
            target_app_data_root: second_target_root.clone(),
            created_at: "2026-04-24T10:01:00Z".to_string(),
        };
        write_pending_migration_if_absent(&config_root, RuntimeMode::Bundled, &existing)
            .expect("existing pending migration should write");

        let error =
            write_pending_migration_if_absent(&config_root, RuntimeMode::Bundled, &attempted)
                .expect_err("existing pending migration should not be overwritten");

        assert!(error.contains("already scheduled"));
        let saved = read_pending_migration(&config_root, RuntimeMode::Bundled)
            .expect("pending migration should read")
            .expect("pending migration should exist");
        assert_eq!(saved.target_app_data_root, first_target_root);
        assert!(pending_temp_files(&config_root).is_empty());

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&source_root);
        remove_dir_if_exists(&first_target_root);
        remove_dir_if_exists(&second_target_root);
    }

    #[test]
    fn scheduling_pending_migration_uses_managed_current_root() {
        let config_root = unique_temp_dir("schedule-config");
        let default_root = unique_temp_dir("schedule-default");
        let current_root = unique_temp_dir("schedule-current");
        let target_root = unique_temp_dir("schedule-target");
        let resource_root = unique_temp_dir("schedule-resource");

        let state = schedule_data_directory_migration(
            RuntimeMode::Bundled,
            &config_root,
            &default_root,
            &current_root,
            Some(&resource_root),
            &target_root,
        )
        .expect("migration scheduling should succeed");

        assert_eq!(
            state.pending_target_app_data_root,
            Some(target_root.clone())
        );
        assert!(!state.migration_allowed);

        let pending = read_pending_migration(&config_root, RuntimeMode::Bundled)
            .expect("pending migration should read")
            .expect("pending migration should exist");
        assert_eq!(pending.source_app_data_root, current_root);
        assert_eq!(pending.target_app_data_root, target_root);
        assert_eq!(pending.runtime_mode, RuntimeMode::Bundled);

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&default_root);
        remove_dir_if_exists(&current_root);
        remove_dir_if_exists(&resource_root);
        remove_dir_if_exists(&pending.target_app_data_root);
    }

    #[test]
    fn scheduling_pending_migration_allows_custom_root_to_move_again() {
        let config_root = unique_temp_dir("schedule-custom-config");
        let default_root = unique_temp_dir("schedule-custom-default");
        let current_root = unique_temp_dir("schedule-custom-current");
        let target_root = unique_temp_dir("schedule-custom-target");
        let config = RuntimeDataDirectoryConfig {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            custom_app_data_root: Some(current_root.clone()),
            default_location_confirmed_at: None,
            migration_completed_at: Some("unix-ms:already".to_string()),
        };
        write_runtime_config(&config_root, &config).expect("runtime config should write");

        let state = schedule_data_directory_migration(
            RuntimeMode::Bundled,
            &config_root,
            &default_root,
            &current_root,
            None,
            &target_root,
        )
        .expect("second migration should be scheduled");

        assert_eq!(
            state.pending_target_app_data_root,
            Some(target_root.clone())
        );
        assert!(!state.migration_allowed);
        let pending = read_pending_migration(&config_root, RuntimeMode::Bundled)
            .expect("pending migration should read")
            .expect("pending migration should exist");
        assert_eq!(pending.source_app_data_root, current_root);
        assert_eq!(pending.target_app_data_root, target_root);

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&default_root);
        remove_dir_if_exists(&pending.source_app_data_root);
        remove_dir_if_exists(&pending.target_app_data_root);
    }

    #[test]
    fn scheduling_pending_migration_rejects_existing_pending_and_preserves_it() {
        let config_root = unique_temp_dir("schedule-existing-pending-config");
        let default_root = unique_temp_dir("schedule-existing-pending-default");
        let current_root = unique_temp_dir("schedule-existing-pending-current");
        let first_target_root = unique_temp_dir("schedule-existing-pending-first-target");
        let second_target_root = unique_temp_dir("schedule-existing-pending-second-target");
        let existing = PendingDataMigration {
            schema_version: 1,
            runtime_mode: RuntimeMode::Bundled,
            source_app_data_root: current_root.clone(),
            target_app_data_root: first_target_root.clone(),
            created_at: "2026-04-24T10:00:00Z".to_string(),
        };
        write_pending_migration_if_absent(&config_root, RuntimeMode::Bundled, &existing)
            .expect("existing pending migration should write");

        let error = schedule_data_directory_migration(
            RuntimeMode::Bundled,
            &config_root,
            &default_root,
            &current_root,
            None,
            &second_target_root,
        )
        .expect_err("second pending migration should be rejected");

        assert!(error.contains("already configured"));
        let saved = read_pending_migration(&config_root, RuntimeMode::Bundled)
            .expect("pending migration should read")
            .expect("pending migration should exist");
        assert_eq!(saved.target_app_data_root, first_target_root);
        assert!(pending_temp_files(&config_root).is_empty());

        remove_dir_if_exists(&config_root);
        remove_dir_if_exists(&default_root);
        remove_dir_if_exists(&current_root);
        remove_dir_if_exists(&first_target_root);
        remove_dir_if_exists(&second_target_root);
    }

    fn pending_temp_files(config_root: &Path) -> Vec<PathBuf> {
        match fs::read_dir(config_root) {
            Ok(entries) => entries
                .filter_map(Result::ok)
                .map(|entry| entry.path())
                .filter(|path| {
                    path.file_name()
                        .and_then(|name| name.to_str())
                        .is_some_and(|name| {
                            name.starts_with(".pending-data-migration.stable.json.")
                                && name.ends_with(".tmp")
                        })
                })
                .collect(),
            Err(_) => Vec::new(),
        }
    }

    fn unique_temp_dir(label: &str) -> PathBuf {
        let id = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("clock should be after unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("lmca-data-dir-{label}-{}-{id}", std::process::id()))
    }

    fn remove_dir_if_exists(path: &Path) {
        let _ = fs::remove_dir_all(path);
    }

    fn deterministic_staging_root_for_test(target_root: &Path) -> PathBuf {
        let parent = target_root.parent().unwrap_or_else(|| Path::new("."));
        let name = target_root
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("data-root");
        parent.join(format!(".lmca-migration-{name}"))
    }
}
