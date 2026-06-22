use crate::app::{PluginBlock, PluginPosition};
use serde::Deserialize;
use crate::config;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::Duration;
use std::io::Read;

#[derive(Deserialize, Debug)]
struct PluginOutput {
    #[allow(dead_code)]
    name: Option<String>,
    lines: Option<Vec<String>>,
    #[serde(default)]
    position: Option<String>,
}

pub fn load_plugins() -> Vec<PluginBlock> {
    let dirs = plugin_dirs();
    let mut results: Vec<PluginBlock> = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for dir in &dirs {
        if !dir.is_dir() {
            continue;
        }
        let mut entries: Vec<_> = match std::fs::read_dir(dir) {
            Ok(e) => e.filter_map(|e| e.ok()).collect(),
            Err(_) => continue,
        };
        entries.sort_by_key(|e| e.file_name());

        for entry in &entries {
            let name = entry.file_name();
            if name.to_string_lossy().starts_with('.') {
                continue;
            }
            if !seen.insert(name.clone()) {
                continue;
            }
            let path = entry.path();

            let Ok(meta) = std::fs::metadata(&path) else { continue };
            if !meta.is_file() {
                continue;
            }

            let mut child = match Command::new(&path)
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .spawn()
            {
                Ok(c) => c,
                Err(_) => continue,
            };

            let start = std::time::Instant::now();
            let timeout = Duration::from_secs(2);
            let output = loop {
                match child.try_wait() {
                    Ok(Some(_)) => {
                        if let Some(mut out) = child.stdout.take() {
                            let mut buf = String::new();
                            let _ = out.read_to_string(&mut buf);
                            break Some(buf);
                        }
                        break None;
                    }
                    Ok(None) => {
                        if start.elapsed() > timeout {
                            let _ = child.kill();
                            eprintln!("[plugin] timeout: {}", name.to_string_lossy());
                            break None;
                        }
                        std::thread::sleep(Duration::from_millis(20));
                    }
                    Err(_) => break None,
                }
            };

            if let Some(stdout) = output {
                for line in stdout.lines() {
                    let line = line.trim();
                    if line.is_empty() {
                        continue;
                    }
                    if let Ok(po) = serde_json::from_str::<PluginOutput>(line) {
                        if let Some(lines) = po.lines {
                            let position = match po.position.as_deref() {
                                Some("left") => PluginPosition::Left,
                                Some("right") => PluginPosition::Right,
                                _ => PluginPosition::Center,
                            };
                            results.push(PluginBlock { lines, position });
                        }
                    }
                }
            }
        }
    }
    results
}

fn plugin_dirs() -> Vec<PathBuf> {
    let mut dirs = Vec::new();

    // ~/.config/my-greeter/plugins/
    if let Some(home) = std::env::var("HOME").ok() {
        dirs.push(PathBuf::from(home).join(".config/my-greeter/plugins"));
    }

    // <exe_dir>/plugins/ (target/release/plugins/)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            dirs.push(parent.join("plugins"));
        }
    }

    // 项目根目录下的 plugins/（解决 greeter 用户 $HOME 不对的问题）
    if let Some(root) = config::project_root() {
        dirs.push(root.join("plugins"));
    }

    dirs
}
