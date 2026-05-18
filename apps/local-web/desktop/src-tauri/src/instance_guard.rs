// Input: app_data_root?????? focus ????  |  Output: ???????????????
// Output: ??????????????????????
// Role: ?????????????????????
// Use: ?????????????????????????????
use serde::{Deserialize, Serialize};
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, Seek, SeekFrom, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::{mpsc, Arc};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

const FOCUS_SIGNAL: &str = "focus";
const FOCUS_ACK: &str = "focused";
const INSTANCE_LOCK_FILE_NAME: &str = "desktop-instance.lock";
const INSTANCE_METADATA_FILE_NAME: &str = "desktop-instance.json";
const LISTENER_POLL_INTERVAL: Duration = Duration::from_millis(50);
const FOCUS_CONNECTION_TIMEOUT: Duration = Duration::from_millis(100);

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct InstanceMetadata {
    pub app_data_root: PathBuf,
    pub focus_port: u16,
}

pub struct ActiveInstanceGuard {
    metadata: InstanceMetadata,
    metadata_path: PathBuf,
    lock_path: PathBuf,
    lock_file: Option<File>,
    shutdown_tx: Option<mpsc::Sender<()>>,
    listener_thread: Option<JoinHandle<()>>,
}

pub enum InstanceGuardResult {
    Primary(ActiveInstanceGuard),
    ExistingInstanceNotified,
}

impl ActiveInstanceGuard {
    pub fn metadata(&self) -> &InstanceMetadata {
        &self.metadata
    }

    pub fn cleanup(&mut self) -> io::Result<()> {
        if let Some(shutdown_tx) = self.shutdown_tx.take() {
            let _ = shutdown_tx.send(());
        }
        if let Some(listener_thread) = self.listener_thread.take() {
            let _ = listener_thread.join();
        }
        self.lock_file.take();
        remove_instance_file_if_matches(&self.metadata_path, &self.metadata)?;
        remove_file_if_exists(&self.lock_path)?;
        Ok(())
    }
}

impl Drop for ActiveInstanceGuard {
    fn drop(&mut self) {
        let _ = self.cleanup();
    }
}

pub fn load_existing_metadata(app_data_root: &Path) -> io::Result<Option<InstanceMetadata>> {
    load_owner_record(app_data_root)
}

pub fn notify_existing_instance(
    metadata: &InstanceMetadata,
    timeout: Duration,
) -> io::Result<bool> {
    let address = SocketAddr::from(([127, 0, 0, 1], metadata.focus_port));
    let mut stream = match TcpStream::connect_timeout(&address, timeout) {
        Ok(stream) => stream,
        Err(error)
            if matches!(
                error.kind(),
                io::ErrorKind::ConnectionRefused
                    | io::ErrorKind::TimedOut
                    | io::ErrorKind::ConnectionAborted
                    | io::ErrorKind::ConnectionReset
                    | io::ErrorKind::AddrNotAvailable
                    | io::ErrorKind::NotFound
            ) =>
        {
            return Ok(false);
        }
        Err(error) => return Err(error),
    };
    stream.set_read_timeout(Some(timeout))?;
    stream.set_write_timeout(Some(timeout))?;
    if stream
        .write_all(format!("{FOCUS_SIGNAL}\n").as_bytes())
        .and_then(|_| stream.flush())
        .is_err()
    {
        return Ok(false);
    }

    let mut response = String::new();
    if BufReader::new(stream).read_line(&mut response).is_err() {
        return Ok(false);
    }

    Ok(response.trim_end() == FOCUS_ACK)
}

pub fn try_acquire_instance_guard<F>(
    app_data_root: &Path,
    timeout: Duration,
    on_focus: F,
) -> io::Result<InstanceGuardResult>
where
    F: Fn() + Send + Sync + 'static,
{
    fs::create_dir_all(app_data_root)?;
    let lock_path = lock_path_for(app_data_root);
    let metadata_path = metadata_path_for(app_data_root);
    let on_focus = Arc::new(on_focus);

    loop {
        if let Some(metadata) = load_owner_record(app_data_root)? {
            if notify_existing_instance(&metadata, timeout)? {
                return Ok(InstanceGuardResult::ExistingInstanceNotified);
            }
            if !lock_path.exists() {
                remove_file_if_exists(&metadata_path)?;
            }
        }

        match try_create_lock_file(&lock_path) {
            Ok(mut lock_file) => {
                let listener = match TcpListener::bind(("127.0.0.1", 0)) {
                    Ok(listener) => listener,
                    Err(error) => {
                        drop(lock_file);
                        let _ = remove_file_if_exists(&lock_path);
                        return Err(error);
                    }
                };
                if let Err(error) = listener.set_nonblocking(true) {
                    drop(lock_file);
                    drop(listener);
                    let _ = remove_file_if_exists(&lock_path);
                    return Err(error);
                }
                let metadata = match listener.local_addr() {
                    Ok(address) => InstanceMetadata {
                        app_data_root: app_data_root.to_path_buf(),
                        focus_port: address.port(),
                    },
                    Err(error) => {
                        drop(lock_file);
                        drop(listener);
                        let _ = remove_file_if_exists(&lock_path);
                        return Err(error);
                    }
                };
                if let Err(error) = write_metadata(&metadata_path, &metadata) {
                    drop(lock_file);
                    drop(listener);
                    let _ = remove_file_if_exists(&lock_path);
                    return Err(error);
                }
                if let Err(error) = write_lock_metadata(&mut lock_file, &metadata) {
                    drop(lock_file);
                    drop(listener);
                    let _ = remove_file_if_exists(&metadata_path);
                    let _ = remove_file_if_exists(&lock_path);
                    return Err(error);
                }
                let (shutdown_tx, shutdown_rx) = mpsc::channel();
                let listener_thread =
                    spawn_focus_listener(listener, shutdown_rx, Arc::clone(&on_focus));

                return Ok(InstanceGuardResult::Primary(ActiveInstanceGuard {
                    metadata,
                    metadata_path,
                    lock_path,
                    lock_file: Some(lock_file),
                    shutdown_tx: Some(shutdown_tx),
                    listener_thread: Some(listener_thread),
                }));
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                if wait_for_live_instance(app_data_root, timeout)? {
                    return Ok(InstanceGuardResult::ExistingInstanceNotified);
                }
                clear_stale_instance_files(app_data_root)?;
            }
            Err(error) => return Err(error),
        }
    }
}

fn wait_for_live_instance(app_data_root: &Path, timeout: Duration) -> io::Result<bool> {
    let deadline = Instant::now() + timeout;

    loop {
        if let Some(metadata) = load_owner_record(app_data_root)? {
            if notify_existing_instance(&metadata, timeout)? {
                return Ok(true);
            }
        }

        if Instant::now() >= deadline {
            return Ok(false);
        }

        thread::sleep(LISTENER_POLL_INTERVAL);
    }
}

fn try_create_lock_file(lock_path: &Path) -> io::Result<File> {
    OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(lock_path)
}

fn write_metadata(metadata_path: &Path, metadata: &InstanceMetadata) -> io::Result<()> {
    let payload = serde_json::to_vec(metadata).map_err(io::Error::other)?;
    fs::write(metadata_path, payload)
}

fn write_lock_metadata(lock_file: &mut File, metadata: &InstanceMetadata) -> io::Result<()> {
    let payload = serde_json::to_vec(metadata).map_err(io::Error::other)?;
    lock_file.set_len(0)?;
    lock_file.seek(SeekFrom::Start(0))?;
    lock_file.write_all(&payload)?;
    lock_file.flush()
}

fn spawn_focus_listener<F>(
    listener: TcpListener,
    shutdown_rx: mpsc::Receiver<()>,
    on_focus: Arc<F>,
) -> JoinHandle<()>
where
    F: Fn() + Send + Sync + 'static,
{
    thread::spawn(move || loop {
        match shutdown_rx.try_recv() {
            Ok(_) | Err(mpsc::TryRecvError::Disconnected) => break,
            Err(mpsc::TryRecvError::Empty) => {}
        }

        match listener.accept() {
            Ok((mut stream, _)) => {
                let _ = handle_focus_connection(&mut stream, on_focus.as_ref());
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                thread::sleep(LISTENER_POLL_INTERVAL);
            }
            Err(_) => {
                thread::sleep(LISTENER_POLL_INTERVAL);
            }
        }
    })
}

fn handle_focus_connection(stream: &mut TcpStream, on_focus: &impl Fn()) -> io::Result<()> {
    stream.set_read_timeout(Some(FOCUS_CONNECTION_TIMEOUT))?;
    stream.set_write_timeout(Some(FOCUS_CONNECTION_TIMEOUT))?;

    let mut request = String::new();
    BufReader::new(stream.try_clone()?).read_line(&mut request)?;
    if request.trim_end() != FOCUS_SIGNAL {
        return Ok(());
    }

    on_focus();
    stream.write_all(format!("{FOCUS_ACK}\n").as_bytes())?;
    stream.flush()
}

fn clear_stale_instance_files(app_data_root: &Path) -> io::Result<()> {
    remove_file_if_exists(&metadata_path_for(app_data_root))?;
    remove_file_if_exists(&lock_path_for(app_data_root))?;
    Ok(())
}

fn load_owner_record(app_data_root: &Path) -> io::Result<Option<InstanceMetadata>> {
    if let Some(metadata) =
        load_instance_record_from_path(&metadata_path_for(app_data_root), app_data_root)?
    {
        return Ok(Some(metadata));
    }

    load_instance_record_from_path(&lock_path_for(app_data_root), app_data_root)
}

fn load_instance_record_from_path(
    path: &Path,
    expected_app_data_root: &Path,
) -> io::Result<Option<InstanceMetadata>> {
    let payload = match fs::read(path) {
        Ok(payload) => payload,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };

    let metadata: InstanceMetadata = match serde_json::from_slice(&payload) {
        Ok(metadata) => metadata,
        Err(_) => return Ok(None),
    };

    if metadata.app_data_root != expected_app_data_root {
        return Ok(None);
    }

    Ok(Some(metadata))
}

fn remove_instance_file_if_matches(
    metadata_path: &Path,
    expected: &InstanceMetadata,
) -> io::Result<()> {
    let existing = match fs::read(metadata_path) {
        Ok(payload) => payload,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error),
    };
    let existing: InstanceMetadata = match serde_json::from_slice(&existing) {
        Ok(metadata) => metadata,
        Err(_) => return remove_file_if_exists(metadata_path),
    };

    if existing == *expected {
        remove_file_if_exists(metadata_path)?;
    }

    Ok(())
}

fn remove_file_if_exists(path: &Path) -> io::Result<()> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    }
}

fn lock_path_for(app_data_root: &Path) -> PathBuf {
    app_data_root.join(INSTANCE_LOCK_FILE_NAME)
}

fn metadata_path_for(app_data_root: &Path) -> PathBuf {
    app_data_root.join(INSTANCE_METADATA_FILE_NAME)
}

#[cfg(test)]
mod tests {
    use super::{
        handle_focus_connection, load_existing_metadata, lock_path_for, metadata_path_for,
        notify_existing_instance, try_acquire_instance_guard, InstanceGuardResult,
        InstanceMetadata,
    };
    use std::fs;
    use std::net::{TcpListener, TcpStream};
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::mpsc;
    use std::sync::Arc;
    use std::thread;
    use std::time::{Duration, SystemTime, UNIX_EPOCH};

    #[test]
    fn load_existing_metadata_reads_saved_focus_port() {
        let app_data_root = unique_temp_dir("load-metadata");
        fs::create_dir_all(&app_data_root).expect("temp dir should exist");
        let metadata = InstanceMetadata {
            app_data_root: app_data_root.clone(),
            focus_port: 43123,
        };
        fs::write(
            metadata_path_for(&app_data_root),
            serde_json::to_vec(&metadata).expect("metadata should serialize"),
        )
        .expect("metadata should write");

        let loaded = load_existing_metadata(&app_data_root).expect("metadata load should succeed");

        assert_eq!(loaded, Some(metadata));
        fs::remove_dir_all(app_data_root).expect("temp dir should clean up");
    }

    #[test]
    fn notify_existing_instance_delivers_focus_signal_to_live_listener() {
        let app_data_root = unique_temp_dir("notify-instance");
        let focus_count = Arc::new(AtomicUsize::new(0));
        let focus_count_clone = Arc::clone(&focus_count);
        let guard =
            try_acquire_instance_guard(&app_data_root, Duration::from_millis(250), move || {
                focus_count_clone.fetch_add(1, Ordering::SeqCst);
            })
            .expect("instance guard should bind");
        let mut guard = match guard {
            InstanceGuardResult::Primary(guard) => guard,
            InstanceGuardResult::ExistingInstanceNotified => {
                panic!("fresh app data root should become the primary instance")
            }
        };

        let notified = notify_existing_instance(guard.metadata(), Duration::from_millis(250))
            .expect("focus notify should succeed");

        assert!(notified);
        assert_eq!(focus_count.load(Ordering::SeqCst), 1);

        guard.cleanup().expect("guard cleanup should succeed");
        fs::remove_dir_all(app_data_root).expect("temp dir should clean up");
    }

    #[test]
    fn try_acquire_instance_guard_replaces_stale_metadata_for_same_data_root() {
        let app_data_root = unique_temp_dir("stale-instance");
        fs::create_dir_all(&app_data_root).expect("temp dir should exist");
        let stale_metadata = InstanceMetadata {
            app_data_root: app_data_root.clone(),
            focus_port: 9,
        };
        fs::write(
            metadata_path_for(&app_data_root),
            serde_json::to_vec(&stale_metadata).expect("metadata should serialize"),
        )
        .expect("metadata should write");

        let guard = try_acquire_instance_guard(&app_data_root, Duration::from_millis(100), || {})
            .expect("stale metadata should be replaceable");
        let mut guard = match guard {
            InstanceGuardResult::Primary(guard) => guard,
            InstanceGuardResult::ExistingInstanceNotified => {
                panic!("stale metadata should not block a new primary instance")
            }
        };
        let loaded = load_existing_metadata(&app_data_root)
            .expect("replacement metadata should load")
            .expect("replacement metadata should exist");

        assert_eq!(loaded.app_data_root, app_data_root);
        assert_ne!(loaded.focus_port, stale_metadata.focus_port);
        assert_eq!(loaded, guard.metadata().clone());

        guard.cleanup().expect("guard cleanup should succeed");
        fs::remove_dir_all(app_data_root).expect("temp dir should clean up");
    }

    #[test]
    fn try_acquire_instance_guard_notifies_live_metadata_even_without_lock_file() {
        let app_data_root = unique_temp_dir("live-metadata-without-lock");
        let focus_count = Arc::new(AtomicUsize::new(0));
        let focus_count_clone = Arc::clone(&focus_count);
        let first_guard =
            try_acquire_instance_guard(&app_data_root, Duration::from_millis(250), move || {
                focus_count_clone.fetch_add(1, Ordering::SeqCst);
            })
            .expect("first instance guard should bind");
        let mut first_guard = match first_guard {
            InstanceGuardResult::Primary(guard) => guard,
            InstanceGuardResult::ExistingInstanceNotified => {
                panic!("fresh app data root should become the primary instance")
            }
        };

        fs::remove_file(lock_path_for(&app_data_root)).expect("lock file should be removable");

        let second_attempt =
            try_acquire_instance_guard(&app_data_root, Duration::from_millis(250), || {})
                .expect("second launch should resolve against live metadata");

        assert!(matches!(
            second_attempt,
            InstanceGuardResult::ExistingInstanceNotified
        ));
        assert_eq!(focus_count.load(Ordering::SeqCst), 1);

        first_guard.cleanup().expect("guard cleanup should succeed");
        fs::remove_dir_all(app_data_root).expect("temp dir should clean up");
    }

    #[test]
    fn try_acquire_instance_guard_notifies_live_owner_when_metadata_is_missing() {
        let app_data_root = unique_temp_dir("live-owner-missing-metadata");
        let focus_count = Arc::new(AtomicUsize::new(0));
        let focus_count_clone = Arc::clone(&focus_count);
        let first_guard =
            try_acquire_instance_guard(&app_data_root, Duration::from_millis(250), move || {
                focus_count_clone.fetch_add(1, Ordering::SeqCst);
            })
            .expect("first instance guard should bind");
        let mut first_guard = match first_guard {
            InstanceGuardResult::Primary(guard) => guard,
            InstanceGuardResult::ExistingInstanceNotified => {
                panic!("fresh app data root should become the primary instance")
            }
        };

        fs::remove_file(metadata_path_for(&app_data_root))
            .expect("metadata file should be removable");

        let second_attempt =
            try_acquire_instance_guard(&app_data_root, Duration::from_millis(250), || {})
                .expect("second launch should resolve against live lock owner");

        assert!(matches!(
            second_attempt,
            InstanceGuardResult::ExistingInstanceNotified
        ));
        assert_eq!(focus_count.load(Ordering::SeqCst), 1);
        assert!(lock_path_for(&app_data_root).exists());

        first_guard.cleanup().expect("guard cleanup should succeed");
        fs::remove_dir_all(app_data_root).expect("temp dir should clean up");
    }

    #[test]
    fn try_acquire_instance_guard_notifies_live_owner_when_metadata_is_corrupt() {
        let app_data_root = unique_temp_dir("live-owner-corrupt-metadata");
        let focus_count = Arc::new(AtomicUsize::new(0));
        let focus_count_clone = Arc::clone(&focus_count);
        let first_guard =
            try_acquire_instance_guard(&app_data_root, Duration::from_millis(250), move || {
                focus_count_clone.fetch_add(1, Ordering::SeqCst);
            })
            .expect("first instance guard should bind");
        let mut first_guard = match first_guard {
            InstanceGuardResult::Primary(guard) => guard,
            InstanceGuardResult::ExistingInstanceNotified => {
                panic!("fresh app data root should become the primary instance")
            }
        };

        fs::write(metadata_path_for(&app_data_root), b"{not-json")
            .expect("corrupt metadata should write");

        let second_attempt =
            try_acquire_instance_guard(&app_data_root, Duration::from_millis(250), || {})
                .expect("second launch should resolve against live lock owner");

        assert!(matches!(
            second_attempt,
            InstanceGuardResult::ExistingInstanceNotified
        ));
        assert_eq!(focus_count.load(Ordering::SeqCst), 1);
        assert!(lock_path_for(&app_data_root).exists());

        first_guard.cleanup().expect("guard cleanup should succeed");
        fs::remove_dir_all(app_data_root).expect("temp dir should clean up");
    }

    #[test]
    fn idle_focus_client_does_not_block_connection_handler_indefinitely() {
        let listener =
            TcpListener::bind(("127.0.0.1", 0)).expect("test listener should bind locally");
        let port = listener
            .local_addr()
            .expect("listener should have address")
            .port();
        let (done_tx, done_rx) = mpsc::channel();
        let worker = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("idle client should connect");
            let result = handle_focus_connection(&mut stream, &|| {});
            let _ = done_tx.send(result.map(|_| ()));
        });
        let idle_stream =
            TcpStream::connect(("127.0.0.1", port)).expect("idle client should connect");

        let result = done_rx.recv_timeout(Duration::from_millis(300));
        drop(idle_stream);
        worker.join().expect("connection worker should finish");

        assert!(
            result.is_ok(),
            "idle accepted focus clients should time out instead of blocking indefinitely"
        );
    }

    fn unique_temp_dir(label: &str) -> std::path::PathBuf {
        let unique_id = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock should be after unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!(
            "ai-memory-card-instance-guard-{label}-{}-{unique_id}",
            std::process::id()
        ))
    }
}
