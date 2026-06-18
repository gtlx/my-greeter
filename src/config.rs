use serde::Deserialize;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Deserialize, Default)]
pub struct Config {
    #[serde(default)]
    pub log: LogConfig,
    #[serde(default)]
    pub auth: AuthConfig,
    #[serde(default)]
    pub branding: BrandingConfig,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LogConfig {
    #[serde(default)]
    pub enable: bool,
    #[serde(default = "default_log_path")]
    pub path: PathBuf,
}

impl Default for LogConfig {
    fn default() -> Self {
        Self {
            enable: false,
            path: default_log_path(),
        }
    }
}

fn default_log_path() -> PathBuf {
    PathBuf::from("/tmp/my-greeter.log")
}

#[derive(Debug, Clone, Deserialize)]
pub struct AuthConfig {
    #[serde(default)]
    pub default_user: String,
    #[serde(default)]
    pub auto_login: bool,
}

impl Default for AuthConfig {
    fn default() -> Self {
        Self {
            default_user: String::new(),
            auto_login: false,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct BrandingConfig {
    #[serde(default = "default_title")]
    pub title: String,
}

impl Default for BrandingConfig {
    fn default() -> Self {
        Self {
            title: default_title(),
        }
    }
}

fn default_title() -> String {
    "Welcome".to_string()
}

/// 从 exe 路径往上找 project 根目录（target/release/my-greeter → 往上2级）
pub fn project_root() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let parent = exe.parent()?;        // target/release/
    let grand = parent.parent()?;       // target/
    Some(grand.parent()?.to_path_buf()) // 项目根目录
}

impl Config {
    pub fn load() -> Self {
        let mut paths = Vec::new();

        paths.push(PathBuf::from("/etc/my-greeter/config.toml"));

        if let Some(cfg_dir) = dirs::config_dir() {
            paths.push(cfg_dir.join("my-greeter/config.toml"));
        }

        paths.push(PathBuf::from("config.toml"));

        // exe 同项目根目录（解决 greeter 用户 $HOME 不对的问题）
        if let Some(root) = project_root() {
            paths.push(root.join("config.toml"));
        }

        for p in &paths {
            if p.exists() {
                if let Ok(content) = std::fs::read_to_string(p) {
                    if let Ok(cfg) = toml::from_str(&content) {
                        return cfg;
                    }
                }
            }
        }
        Config::default()
    }
}

mod dirs {
    use std::path::PathBuf;

    pub fn config_dir() -> Option<PathBuf> {
        std::env::var("XDG_CONFIG_HOME")
            .ok()
            .map(PathBuf::from)
            .or_else(|| {
                std::env::var("HOME")
                    .ok()
                    .map(|h| PathBuf::from(h).join(".config"))
            })
    }
}
