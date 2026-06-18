use crate::app::{App, Focus};
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout},
    style::{Color, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

const FIELD_WIDTH: u16 = 48;

pub fn render(f: &mut Frame, app: &App) {
    let area = f.size();

    // Layout: like Lemurs chunks
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .horizontal_margin(2)
        .vertical_margin(1)
        .constraints([
            Constraint::Length(1),      // title
            Constraint::Length(1),      // gap or plugin
            Constraint::Length(1),      // plugin lines (or gap)
            Constraint::Length(1),      // gap
            Constraint::Length(1),      // session switcher
            Constraint::Length(1),      // gap
            Constraint::Length(3),      // username field
            Constraint::Length(1),      // gap
            Constraint::Length(3),      // password field
            Constraint::Length(1),      // error message
            Constraint::Length(1),      // hint bar
            Constraint::Min(0),         // remaining
        ])
        .split(area);

    let title_color = Style::default().fg(Color::Cyan).add_modifier(ratatui::style::Modifier::BOLD);
    let env_color = Style::default().fg(Color::DarkGray);
    let env_focused = Style::default().fg(Color::White).add_modifier(ratatui::style::Modifier::BOLD);
    let border_color = Style::default().fg(Color::White);
    let border_focused = Style::default().fg(Color::from_u32(0xFFA500)); // orange
    let content_color = Style::default().fg(Color::White);
    let content_focused = Style::default().fg(Color::from_u32(0xFFA500));
    let hint_color = Style::default().fg(Color::DarkGray);
    let error_color = Style::default().fg(Color::Red).add_modifier(ratatui::style::Modifier::BOLD);

    // ── Title ──
    let title_text = format!("  {}", app.config.branding.title);
    let title = Paragraph::new(Text::from(Line::from(Span::styled(title_text, title_color))))
        .alignment(Alignment::Left);
    f.render_widget(title, chunks[0]);

    // ── Plugin lines ──
    let plug_color = Style::default().fg(Color::Green);
    if !app.plugin_lines.is_empty() {
        let plug_text: Vec<Line> = app.plugin_lines.iter()
            .map(|l| Line::from(Span::styled(format!("  {}", l), plug_color)))
            .collect();
        let plug = Paragraph::new(Text::from(plug_text)).alignment(Alignment::Left);
        f.render_widget(plug, chunks[2]);
    }

    // ── Session switcher ──
    let is_sess_focused = app.focus == Focus::Session;
    let sess = app.current_session();
    let sess_style = if is_sess_focused { env_focused } else { env_color };
    // Show: "< name >" centered
    let sess_text = format!("  < {} >  ", sess.name);
    let sess_para = Paragraph::new(Text::from(Line::from(Span::styled(sess_text, sess_style))))
        .alignment(Alignment::Center);
    f.render_widget(sess_para, chunks[4]);

    // ── Username field ──
    let is_user_focused = app.focus == Focus::Username;
    let user_border = if is_user_focused { border_focused } else { border_color };
    let user_content = if is_user_focused { content_focused } else { content_color };

    let user_display = if app.username.is_empty() {
        String::new()
    } else {
        app.username.clone()
    };

    let user_block = Block::default()
        .title(" Login ")
        .borders(Borders::ALL)
        .border_style(user_border);

    let user_para = Paragraph::new(Text::from(Line::from(
        Span::styled(user_display.clone(), user_content)
    )))
    .block(user_block)
    .alignment(Alignment::Left);
    f.render_widget(user_para, chunks[6]);

    // Set cursor position for username
    if is_user_focused {
        let cursor_x = chunks[6].x + 2 + user_display.len() as u16;
        let cursor_y = chunks[6].y + 1;
        f.set_cursor(cursor_x, cursor_y);
    }

    // ── Password field ──
    let is_pwd_focused = app.focus == Focus::Password;
    let pwd_border = if is_pwd_focused { border_focused } else { border_color };
    let pwd_content = if is_pwd_focused { content_focused } else { content_color };

    let pwd_display: String = app.password.chars().map(|_| '*').collect();

    let pwd_block = Block::default()
        .title(" Password ")
        .borders(Borders::ALL)
        .border_style(pwd_border);

    let pwd_para = Paragraph::new(Text::from(Line::from(
        Span::styled(pwd_display.clone(), pwd_content)
    )))
    .block(pwd_block)
    .alignment(Alignment::Left);
    f.render_widget(pwd_para, chunks[8]);

    // Set cursor position for password
    if is_pwd_focused {
        let cursor_x = chunks[8].x + 2 + pwd_display.len() as u16;
        let cursor_y = chunks[8].y + 1;
        f.set_cursor(cursor_x, cursor_y);
    }

    // ── Error message ──
    if !app.error_msg.is_empty() {
        let err_para = Paragraph::new(Text::from(Line::from(
            Span::styled(format!("  {}", app.error_msg), error_color)
        )))
        .alignment(Alignment::Left);
        f.render_widget(err_para, chunks[9]);
    }

    // ── Hint bar ──
    let hint_text = "  Tab:Focus  ←→:Session  Enter:Next";
    let hint_para = Paragraph::new(Text::from(Line::from(
        Span::styled(hint_text, hint_color)
    )))
    .alignment(Alignment::Left);
    f.render_widget(hint_para, chunks[10]);
}
