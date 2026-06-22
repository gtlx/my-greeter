use serde::Deserialize;
use std::path::PathBuf;

#[derive(Debug, Clone, Deserialize, Default)]
pub struct Config {
    #[serde(default)]
    pub log: LogConfig,
    #[serde(default)]
    pub auth: AuthConfig,
    #[serde(default)]
    pub branding: BrandingConfig,
    #[serde(default)]
    pub theme: Theme,
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
        Self { enable: false, path: default_log_path() }
    }
}

fn default_log_path() -> PathBuf { PathBuf::from("/tmp/my-greeter.log") }

#[derive(Debug, Clone, Deserialize)]
pub struct AuthConfig {
    #[serde(default)]
    pub default_user: String,
    #[serde(default)]
    #[allow(dead_code)]
    pub auto_login: bool,
}

impl Default for AuthConfig {
    fn default() -> Self {
        Self { default_user: String::new(), auto_login: false }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct BrandingConfig {
    #[serde(default = "default_title")]
    pub title: String,
}

impl Default for BrandingConfig {
    fn default() -> Self { Self { title: default_title() } }
}

fn default_title() -> String { "Welcome".to_string() }

// ─── 主题系统 ─────────────────────────────────────────

#[derive(Debug, Clone, Deserialize)]
pub struct Theme {
    #[serde(default = "t_default")]
    pub title: String,
    #[serde(default = "s_default")]
    pub separator: String,
    #[serde(default = "b_default")]
    pub border: String,
    #[serde(default = "bf_default")]
    pub border_focus: String,
    #[serde(default = "t_default")]
    pub text: String,
    #[serde(default = "bf_default")]
    pub text_focus: String,
    #[serde(default = "g_default")]
    pub plugin: String,
    #[serde(default = "h_default")]
    pub hint: String,
    #[serde(default = "er_default")]
    pub error: String,
    #[serde(default = "s_default")]
    pub session: String,
    #[serde(default = "sf_default")]
    pub session_focus: String,
    #[serde(default = "panel_title_default")]
    pub panel_title: String,
    #[serde(default = "accent_default")]
    pub accent: String,
    #[serde(default)]
    pub background: String,
    #[serde(default = "layout_default")]
    pub layout: String,
}

fn t_default() -> String { "white".to_string() }
fn s_default() -> String { "dark gray".to_string() }
fn b_default() -> String { "white".to_string() }
fn bf_default() -> String { "orange".to_string() }
fn g_default() -> String { "green".to_string() }
fn h_default() -> String { "dark gray".to_string() }
fn er_default() -> String { "red bold".to_string() }
fn sf_default() -> String { "white bold".to_string() }
fn panel_title_default() -> String { "cyan bold".to_string() }
fn accent_default() -> String { "#FFA500".to_string() }
fn layout_default() -> String { "auto".to_string() }

impl Default for Theme {
    fn default() -> Self {
        Self {
            title: "cyan bold".to_string(),
            separator: "dark gray".to_string(),
            border: "white".to_string(),
            border_focus: "#FFA500".to_string(),
            text: "white".to_string(),
            text_focus: "#FFA500".to_string(),
            plugin: "green".to_string(),
            hint: "dark gray".to_string(),
            error: "red bold".to_string(),
            session: "dark gray".to_string(),
            session_focus: "white bold".to_string(),
            panel_title: "cyan bold".to_string(),
            accent: "#FFA500".to_string(),
            background: String::new(),
            layout: "auto".to_string(),
        }
    }
}

/// 将样式字符串 "cyan bold" 或 "#FFA500" 解析为 ratatui Style
pub fn parse_style(s: &str) -> ratatui::style::Style {
    use ratatui::style::{Color, Modifier, Style};
    let parts: Vec<&str> = s.split_whitespace().collect();
    let mut color = Color::White;
    let mut modifier = Modifier::empty();

    for p in &parts {
        let p = p.to_lowercase();
        match p.as_str() {
            "black" => color = Color::Black,
            "red" => color = Color::Red,
            "green" => color = Color::Green,
            "yellow" => color = Color::Yellow,
            "blue" => color = Color::Blue,
            "magenta" => color = Color::Magenta,
            "cyan" => color = Color::Cyan,
            "white" => color = Color::White,
            "gray" | "grey" => color = Color::Gray,
            "dark_gray" | "darkgray" => color = Color::DarkGray,
            "light_red" | "lightred" => color = Color::LightRed,
            "light_green" | "lightgreen" => color = Color::LightGreen,
            "light_yellow" | "lightyellow" => color = Color::LightYellow,
            "light_blue" | "lightblue" => color = Color::LightBlue,
            "light_magenta" | "lightmagenta" => color = Color::LightMagenta,
            "light_cyan" | "lightcyan" => color = Color::LightCyan,
            "orange" => color = Color::from_u32(0xFFA500),
            "bold" => modifier |= Modifier::BOLD,
            "dim" => modifier |= Modifier::DIM,
            "italic" => modifier |= Modifier::ITALIC,
            "underline" | "underlined" => modifier |= Modifier::UNDERLINED,
            _ if p.starts_with('#') && p.len() == 7 => {
                if let Ok(v) = u32::from_str_radix(&p[1..], 16) {
                    color = Color::from_u32(v);
                }
            }
            _ => {}
        }
    }
    Style::default().fg(color).add_modifier(modifier)
}

// ─── 配置加载 ─────────────────────────────────────────

pub fn project_root() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let parent = exe.parent()?;
    let grand = parent.parent()?;
    Some(grand.parent()?.to_path_buf())
}

impl Config {
    pub fn load() -> Self {
        let mut paths = Vec::new();
        paths.push(PathBuf::from("/etc/my-greeter/config.toml"));
        if let Some(cfg_dir) = dirs::config_dir() {
            paths.push(cfg_dir.join("my-greeter/config.toml"));
        }
        paths.push(PathBuf::from("config.toml"));
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
        std::env::var("XDG_CONFIG_HOME").ok().map(PathBuf::from)
            .or_else(|| std::env::var("HOME").ok().map(|h| PathBuf::from(h).join(".config")))
    }
}
