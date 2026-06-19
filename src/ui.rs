use crate::app::{App, Focus};
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout},
    style::{Color, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

pub fn render(f: &mut Frame, app: &App) {
    let area = f.size();

    // 动态构建 constraints（参考 Lemurs 固定高度布局）
    let n = app.plugin_lines.len();
    let mut c = Vec::new();

    // 0: title
    c.push(Constraint::Length(1));
    // 1..n: plugins (may be 0..0 if empty)
    for _ in 0..n {
        c.push(Constraint::Length(1));
    }
    // n+1: gap
    c.push(Constraint::Length(1));
    // n+2: session switcher
    c.push(Constraint::Length(1));
    // n+3: gap
    c.push(Constraint::Length(1));
    // n+4: username field (3 lines: top, content, bottom)
    c.push(Constraint::Length(3));
    // n+5: gap
    c.push(Constraint::Length(1));
    // n+6: password field (3 lines)
    c.push(Constraint::Length(3));
    // n+7: gap
    c.push(Constraint::Length(1));
    // n+8: hint bar
    c.push(Constraint::Length(1));
    // 剩余空间 → 自动居中
    c.push(Constraint::Min(0));

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .horizontal_margin(2)
        .vertical_margin(1)
        .constraints(c)
        .split(area);

    // 各个 widget 的 index
    let idx_title = 0;
    let idx_plugin_start = 1;
    let idx_gap1 = n + 1;
    let idx_session = n + 2;
    let idx_gap2 = n + 3;
    let idx_user = n + 4;
    let idx_gap3 = n + 5;
    let idx_pwd = n + 6;
    let idx_gap4 = n + 7;
    let idx_hint = n + 8;

    let title_color = Style::default().fg(Color::Cyan).add_modifier(ratatui::style::Modifier::BOLD);
    let env_color = Style::default().fg(Color::DarkGray);
    let env_focused = Style::default().fg(Color::White).add_modifier(ratatui::style::Modifier::BOLD);
    let border_color = Style::default().fg(Color::White);
    let border_focused = Style::default().fg(Color::from_u32(0xFFA500));
    let content_color = Style::default().fg(Color::White);
    let content_focused = Style::default().fg(Color::from_u32(0xFFA500));
    let hint_color = Style::default().fg(Color::DarkGray);
    let error_color = Style::default().fg(Color::Red).add_modifier(ratatui::style::Modifier::BOLD);
    let plug_color = Style::default().fg(Color::Green);

    // ── Title ──
    let title = Paragraph::new(Line::from(
        Span::styled(format!("  {}", app.config.branding.title), title_color)
    ));
    f.render_widget(title, chunks[idx_title]);

    // ── Plugin lines ──
    if !app.plugin_lines.is_empty() {
        for (i, line) in app.plugin_lines.iter().enumerate() {
            let plug = Paragraph::new(Line::from(
                Span::styled(format!("  {}", line), plug_color)
            )).alignment(Alignment::Center);
            f.render_widget(plug, chunks[idx_plugin_start + i]);
        }
    }

    // ── Session ──
    let sess_sty = if app.focus == Focus::Session { env_focused } else { env_color };
    let sess = Paragraph::new(Line::from(
        Span::styled(format!("  < {} >  ", app.current_session().name), sess_sty)
    )).alignment(Alignment::Center);
    f.render_widget(sess, chunks[idx_session]);

    // ── Username ──
    let u_focus = app.focus == Focus::Username;
    let u_block = Block::default()
        .title(" Login ")
        .borders(Borders::ALL)
        .border_style(if u_focus { border_focused } else { border_color });
    let u_para = Paragraph::new(Line::from(
        Span::styled(app.username.clone(), if u_focus { content_focused } else { content_color })
    )).block(u_block);
    f.render_widget(u_para, chunks[idx_user]);
    if u_focus {
        let x = chunks[idx_user].x + 2 + app.username.len() as u16;
        let y = chunks[idx_user].y + 1;
        f.set_cursor(x, y);
    }

    // ── Password ──
    let p_focus = app.focus == Focus::Password;
    let stars: String = app.password.chars().map(|_| '*').collect();
    let p_block = Block::default()
        .title(" Password ")
        .borders(Borders::ALL)
        .border_style(if p_focus { border_focused } else { border_color });
    let p_para = Paragraph::new(Line::from(
        Span::styled(stars.clone(), if p_focus { content_focused } else { content_color })
    )).block(p_block);
    f.render_widget(p_para, chunks[idx_pwd]);
    if p_focus {
        let x = chunks[idx_pwd].x + 2 + stars.len() as u16;
        let y = chunks[idx_pwd].y + 1;
        f.set_cursor(x, y);
    }

    // ── Error ──
    if !app.error_msg.is_empty() {
        let err = Paragraph::new(Line::from(
            Span::styled(format!("  {}", app.error_msg), error_color)
        ));
        f.render_widget(err, chunks[idx_gap4]); // reuse gap4 as error slot
    }

    // ── Hint ──
    let hint = Paragraph::new(Line::from(
        Span::styled("  F1:Shutdown  F2:Reboot  Tab:Focus  \u{2190}\u{2192}:Session  Enter:Next  Ctrl+U:Clear", hint_color)
    ));
    f.render_widget(hint, chunks[idx_hint]);
}
