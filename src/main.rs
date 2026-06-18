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

    // Init log
    if cfg.log.enable {
        if let Ok(file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&cfg.log.path)
        {
            // Simple log: just write to file directly later
            let _ = file;
        }
    }

    // Check if preview mode
    let preview = std::env::args().any(|a| a == "--preview");

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;
    terminal.hide_cursor()?;

    let mut app = App::new(cfg);

    // Main loop
    let result = run(&mut terminal, &mut app, preview);

    // Cleanup
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
    // Initial draw
    terminal.draw(|f| ui::render(f, app))?;

    while app.running {
        if let Event::Key(key) = event::read()? {
            match (key.code, &app.focus, key.modifiers) {
                // ── Focus cycling ──
                (KeyCode::Tab, _, _) => {
                    app.focus_next();
                }
                (KeyCode::BackTab, _, _) | (KeyCode::Tab, _, KeyModifiers::SHIFT) => {
                    app.focus_prev();
                }

                // ── Session switching ──
                (KeyCode::Left, Focus::Session, _) => {
                    app.prev_session();
                }
                (KeyCode::Right, Focus::Session, _) => {
                    app.next_session();
                }

                // ── Enter ──
                (KeyCode::Enter, Focus::Username, _) => {
                    if !app.username.is_empty() {
                        app.focus = Focus::Password;
                    }
                }
                (KeyCode::Enter, Focus::Password, _) => {
                    if !app.password.is_empty() {
                        if preview {
                            app.error_msg = "[Preview] Auth would proceed now".to_string();
                        } else {
                            match crate::ipc::GreetdClient::connect() {
                                Ok(mut client) => {
                                    match app.submit(&mut client) {
                                        Ok(()) => {
                                            if app.authenticated {
                                                match app.launch(&mut client) {
                                                    Ok(()) => {}
                                                    Err(e) => {
                                                        app.error_msg = format!("Launch error: {}", e);
                                                    }
                                                }
                                            }
                                        }
                                        Err(e) => {
                                            app.error_msg = e;
                                            app.password.clear();
                                        }
                                    }
                                }
                                Err(e) => {
                                    app.error_msg = e;
                                }
                            }
                        }
                    }
                }
                (KeyCode::Enter, Focus::Session, _) => {
                    app.focus = Focus::Username;
                }

                // ── Esc ──
                (KeyCode::Esc, Focus::Session, _) => {
                    if preview {
                        app.running = false;
                    }
                }
                (KeyCode::Esc, _, _) => {
                    app.focus = Focus::Session;
                }

                // ── Quit ──
                (KeyCode::Char('q'), _, _) => {
                    app.running = false;
                }

                // ── Backspace ──
                (KeyCode::Backspace, _, _) => {
                    app.backspace();
                }

                // ── Type characters ──
                (KeyCode::Char(c), _, _) => {
                    app.type_char(c);
                }

                _ => {}
            }

            terminal.draw(|f| ui::render(f, app))?;
        }
    }

    Ok(())
}
