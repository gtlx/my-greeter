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

impl Config {
    pub fn load() -> Self {
        let paths = [
            Path::new("/etc/my-greeter/config.toml"),
            &dirs::config_dir()
                .unwrap_or_else(|| PathBuf::from("."))
                .join("my-greeter/config.toml"),
            &Path::new("config.toml"),
        ];

        for p in &paths {
            if p.exists() {
                let content = std::fs::read_to_string(p).unwrap_or_default();
                if let Ok(cfg) = toml::from_str(&content) {
                    return cfg;
                }
            }
        }
        Config::default()
    }
}

// For dirs::config_dir fallback
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
