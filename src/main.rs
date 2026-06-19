mod app;
mod config;
mod ipc;
mod plugins;
mod ui;

use app::{App, Focus};
use crossterm::{
    event::{self, Event, KeyCode, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};
use std::io;

fn main() -> io::Result<()> {
    let cfg = config::Config::load();

    if cfg.log.enable {
        std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&cfg.log.path)
            .ok();
    }

    let preview = std::env::args().any(|a| a == "--preview");

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;
    terminal.hide_cursor()?;

    let mut app = App::new(cfg);
    let result = run(&mut terminal, &mut app, preview);

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    result
}

fn run(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    app: &mut App,
    preview: bool,
) -> io::Result<()> {
    terminal.draw(|f| ui::render(f, app))?;

    while app.running {
        if let Event::Key(key) = event::read()? {
            match (key.code, &app.focus, key.modifiers) {
                // ── Power: F1=shutdown, F2=reboot ──
                (KeyCode::F(1), _, _) => {
                    drop(terminal);
                    disable_raw_mode()?;
                    execute!(io::stdout(), LeaveAlternateScreen)?;
                    std::process::Command::new("systemctl")
                        .args(["poweroff"]).status().ok();
                    std::process::exit(0);
                }
                (KeyCode::F(2), _, _) => {
                    drop(terminal);
                    disable_raw_mode()?;
                    execute!(io::stdout(), LeaveAlternateScreen)?;
                    std::process::Command::new("systemctl")
                        .args(["reboot"]).status().ok();
                    std::process::exit(0);
                }

                // ── Focus: Tab/Up/Down (同 Lemurs) ──
                (KeyCode::Tab, _, _) => app.focus_next(),
                (KeyCode::Down, _, _) => app.focus_next(),
                (KeyCode::BackTab, _, _) | (KeyCode::Up, _, _) => app.focus_prev(),
                (KeyCode::Tab, _, KeyModifiers::SHIFT) => app.focus_prev(),

                // ── Session: ← →  (同 Lemurs: Left/Right) ──
                (KeyCode::Left, _, _) if app.focus == Focus::Session => app.prev_session(),
                (KeyCode::Right, _, _) if app.focus == Focus::Session => app.next_session(),

                // ── Enter ──
                (KeyCode::Enter, Focus::Session, _) => app.focus = Focus::Username,
                (KeyCode::Enter, Focus::Username, _) if !app.username.is_empty() => {
                    app.focus = Focus::Password;
                }
                (KeyCode::Enter, Focus::Password, _) => {
                    if !app.password.is_empty() {
                        if preview {
                            app.error_msg = "[Preview] Auth would proceed now".to_string();
                        } else if let Ok(mut client) = crate::ipc::GreetdClient::connect() {
                            match app.submit(&mut client) {
                                Ok(()) if app.authenticated => {
                                    if let Err(e) = app.launch(&mut client) {
                                        app.error_msg = format!("Launch error: {}", e);
                                    }
                                }
                                Err(e) => { app.error_msg = e; app.password.clear(); }
                                _ => {}
                            }
                        } else {
                            app.error_msg = "Cannot connect to greetd".to_string();
                        }
                    }
                }

                // ── Esc: 回到 Session / 退出预览 ──
                (KeyCode::Esc, Focus::Session, _) if preview => app.running = false,
                (KeyCode::Esc, _, _) => app.focus = Focus::Session,

                // ── Quit ──
                (KeyCode::Char('q'), Focus::Session, _) => app.running = false,

                // ── 文本编辑键 (同 Lemurs) ──
                (KeyCode::Backspace, _, _) => app.backspace(),
                (KeyCode::Char('h'), _, KeyModifiers::CONTROL) => app.backspace(), // Ctrl+H
                (KeyCode::Char('u'), _, KeyModifiers::CONTROL) => app.clear_field(), // Ctrl+U
                (KeyCode::Char('l'), _, KeyModifiers::CONTROL) => app.clear_field(), // Ctrl+L

                // ── 普通字符输入 ──
                (KeyCode::Char(c), _, _) => app.type_char(c),

                _ => {}
            }
            terminal.draw(|f| ui::render(f, app))?;
        }
    }
    Ok(())
}
