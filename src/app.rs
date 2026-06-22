use crate::config::Config;
use crate::ipc::GreetdClient;
use std::path::Path;

#[derive(Debug, Clone, PartialEq)]
pub enum Focus {
    Session,
    Username,
    Password,
}

#[derive(Debug, Clone, PartialEq)]
pub enum PluginPosition {
    Left,
    Center,
    Right,
}

#[derive(Debug, Clone)]
pub struct PluginBlock {
    pub lines: Vec<String>,
    pub position: PluginPosition,
}

#[derive(Debug, Clone)]
pub struct Session {
    pub name: String,
    pub exec: String,
}

pub struct App {
    pub config: Config,
    pub sessions: Vec<Session>,
    pub session_idx: usize,
    pub username: String,
    pub password: String,
    pub password_visible: bool,
    pub focus: Focus,
    pub plugins: Vec<PluginBlock>,
    pub error_msg: String,
    pub running: bool,
    pub authenticated: bool,
}

impl App {
    pub fn new(config: Config) -> Self {
        let sessions = Self::scan_sessions();
        let default_user = config.auth.default_user.clone();

        let focus = if default_user.is_empty() {
            Focus::Username
        } else {
            Focus::Password
        };

        let plugins = crate::plugins::load_plugins();

        Self {
            config,
            sessions,
            session_idx: 0,
            username: default_user,
            password: String::new(),
            password_visible: false,
            focus,
            plugins,
            error_msg: String::new(),
            running: true,
            authenticated: false,
        }
    }

    fn scan_sessions() -> Vec<Session> {
        let mut sessions = Vec::new();

        // Wayland sessions
        let wayland_dir = Path::new("/usr/share/wayland-sessions");
        if wayland_dir.is_dir() {
            if let Ok(entries) = std::fs::read_dir(wayland_dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.extension().map(|e| e == "desktop").unwrap_or(false) {
                        if let Some(s) = parse_desktop(&path) {
                            sessions.push(s);
                        }
                    }
                }
            }
        }

        // X11 sessions
        let x11_dir = Path::new("/usr/share/xsessions");
        if x11_dir.is_dir() {
            if let Ok(entries) = std::fs::read_dir(x11_dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.extension().map(|e| e == "desktop").unwrap_or(false) {
                        if let Some(s) = parse_desktop(&path) {
                            sessions.push(s);
                        }
                    }
                }
            }
        }

        // Sort by name
        sessions.sort_by(|a, b| a.name.cmp(&b.name));

        // Always add shell as last option
        sessions.push(Session {
            name: "sh".to_string(),
            exec: "/bin/sh".to_string(),
        });

        sessions
    }

    pub fn prev_session(&mut self) {
        if self.session_idx > 0 {
            self.session_idx -= 1;
        }
    }

    pub fn next_session(&mut self) {
        if self.session_idx + 1 < self.sessions.len() {
            self.session_idx += 1;
        }
    }

    pub fn current_session(&self) -> &Session {
        &self.sessions[self.session_idx]
    }

    pub fn focus_next(&mut self) {
        self.focus = match self.focus {
            Focus::Session => Focus::Username,
            Focus::Username => Focus::Password,
            Focus::Password => Focus::Password,
        };
    }

    pub fn focus_prev(&mut self) {
        self.focus = match self.focus {
            Focus::Session => Focus::Session,
            Focus::Username => Focus::Session,
            Focus::Password => Focus::Username,
        };
    }

    pub fn type_char(&mut self, c: char) {
        match self.focus {
            Focus::Username => {
                self.username.push(c);
                self.error_msg.clear();
            }
            Focus::Password => {
                self.password.push(c);
                self.error_msg.clear();
            }
            _ => {}
        }
    }

    pub fn backspace(&mut self) {
        match self.focus {
            Focus::Username => { self.username.pop(); }
            Focus::Password => { self.password.pop(); }
            _ => {}
        }
    }

    pub fn clear_field(&mut self) {
        match self.focus {
            Focus::Username => self.username.clear(),
            Focus::Password => self.password.clear(),
            _ => {}
        }
    }

    pub fn submit(&mut self, client: &mut GreetdClient) -> Result<(), String> {
        if self.username.is_empty() || self.password.is_empty() {
            return Err("empty fields".to_string());
        }

        // Create session
        let resp = client.create_session(&self.username)
            .map_err(|e| e.to_string())?;

        match resp {
            crate::ipc::Response::AuthMessage { auth_message_type, .. } => {
                if auth_message_type == "secret" {
                    let resp = client.auth_response(Some(&self.password))
                        .map_err(|e| e.to_string())?;
                    match resp {
                        crate::ipc::Response::Success => {
                            self.authenticated = true;
                            Ok(())
                        }
                        crate::ipc::Response::Error { description, .. } => {
                            Err(description.unwrap_or_else(|| "auth error".to_string()))
                        }
                        crate::ipc::Response::AuthMessage { .. } => {
                            // Handle additional PAM messages
                            let resp = client.auth_response(None)
                                .map_err(|e| e.to_string())?;
                            match resp {
                                crate::ipc::Response::Success => {
                                    self.authenticated = true;
                                    Ok(())
                                }
                                crate::ipc::Response::Error { description, .. } => {
                                    Err(description.unwrap_or_else(|| "auth error".to_string()))
                                }
                                _ => Err("unexpected response".to_string()),
                            }
                        }
                    }
                } else {
                    Err("unexpected auth message type".to_string())
                }
            }
            crate::ipc::Response::Error { description, .. } => {
                Err(description.unwrap_or_else(|| "create session error".to_string()))
            }
            crate::ipc::Response::Success => {
                self.authenticated = true;
                Ok(())
            }
        }
    }

    pub fn launch(&self, client: &mut GreetdClient) -> Result<(), String> {
        let session = self.current_session();
        let cmd = session.exec.split_whitespace()
            .map(|s| s.to_string())
            .collect::<Vec<_>>();

        let _resp = client.start_session(&cmd, &[])
            .map_err(|e| e.to_string())?;

        // After successful start_session, exit
        std::process::exit(0);
    }
}

fn parse_desktop(path: &Path) -> Option<Session> {
    use std::io::BufRead;

    let file = std::fs::File::open(path).ok()?;
    let reader = std::io::BufReader::new(file);

    let mut in_entry = false;
    let mut name = String::new();
    let mut exec = String::new();

    for line in reader.lines() {
        let line = line.ok()?;
        let line = line.trim().to_string();

        if line == "[Desktop Entry]" {
            in_entry = true;
            continue;
        }
        if !in_entry {
            continue;
        }
        if line.starts_with('[') {
            break;
        }

        if let Some(val) = line.strip_prefix("Name=") {
            name = val.to_string();
        } else if let Some(val) = line.strip_prefix("Exec=") {
            exec = val.to_string();
        }
    }

    if !exec.is_empty() {
        if name.is_empty() {
            name = path.file_stem()?.to_string_lossy().to_string();
        }
        Some(Session { name, exec })
    } else {
        None
    }
}
