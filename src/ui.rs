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

    // ── 动态 constraints：上下 Min(0) 平分空间 → 真正居中 ──
    let n = app.plugin_lines.len();
    let mut c = Vec::new();

    c.push(Constraint::Min(0));          // 0: 上半弹性空间
    c.push(Constraint::Length(1));       // 1: title
    for _ in 0..n {
        c.push(Constraint::Length(1));   // 2..n+1: plugins (动态)
    }
    c.push(Constraint::Length(1));       // n+2: gap
    c.push(Constraint::Length(1));       // n+3: session
    c.push(Constraint::Length(1));       // n+4: gap
    c.push(Constraint::Length(3));       // n+5: username field
    c.push(Constraint::Length(1));       // n+6: gap
    c.push(Constraint::Length(3));       // n+7: password field
    c.push(Constraint::Length(1));       // n+8: gap/error
    c.push(Constraint::Length(1));       // n+9: hint
    c.push(Constraint::Min(0));          // n+10: 下半弹性空间

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .horizontal_margin(2)
        .vertical_margin(0)
        .constraints(c)
        .split(area);

    // widget index (基于 n 偏移)
    let idx_title = 1;
    let idx_plugin_start = 2;
    let idx_session = n + 3;
    let idx_user = n + 5;
    let idx_pwd = n + 7;
    let idx_err = n + 8;
    let idx_hint = n + 9;

    // ── 颜色 ──
    let title_c = Style::default().fg(Color::Cyan).add_modifier(ratatui::style::Modifier::BOLD);
    let env_c = Style::default().fg(Color::DarkGray);
    let env_f = Style::default().fg(Color::White).add_modifier(ratatui::style::Modifier::BOLD);
    let bdr_c = Style::default().fg(Color::White);
    let bdr_f = Style::default().fg(Color::from_u32(0xFFA500));
    let txt_c = Style::default().fg(Color::White);
    let txt_f = Style::default().fg(Color::from_u32(0xFFA500));
    let hint_c = Style::default().fg(Color::DarkGray);
    let err_c = Style::default().fg(Color::Red).add_modifier(ratatui::style::Modifier::BOLD);
    let plug_c = Style::default().fg(Color::Green);

    // ── Title ──
    let title = Paragraph::new(Line::from(
        Span::styled(format!("  {}", app.config.branding.title), title_c)
    ));
    f.render_widget(title, chunks[idx_title]);

    // ── Plugins ──
    for (i, line) in app.plugin_lines.iter().enumerate() {
        let plug = Paragraph::new(Line::from(
            Span::styled(format!("  {}", line), plug_c)
        )).alignment(Alignment::Center);
        f.render_widget(plug, chunks[idx_plugin_start + i]);
    }

    // ── Session ──
    let s_sty = if app.focus == Focus::Session { env_f } else { env_c };
    let sess = Paragraph::new(Line::from(
        Span::styled(format!("  < {} >  ", app.current_session().name), s_sty)
    )).alignment(Alignment::Center);
    f.render_widget(sess, chunks[idx_session]);

    // ── Username ──
    let u_on = app.focus == Focus::Username;
    let u_block = Block::default()
        .title(" Login ")
        .borders(Borders::ALL)
        .border_style(if u_on { bdr_f } else { bdr_c });
    let u_para = Paragraph::new(Line::from(
        Span::styled(app.username.clone(), if u_on { txt_f } else { txt_c })
    )).block(u_block);
    f.render_widget(u_para, chunks[idx_user]);
    if u_on {
        f.set_cursor(chunks[idx_user].x + 2 + app.username.len() as u16, chunks[idx_user].y + 1);
    }

    // ── Password ──
    let p_on = app.focus == Focus::Password;
    let stars: String = app.password.chars().map(|_| '*').collect();
    let p_block = Block::default()
        .title(" Password ")
        .borders(Borders::ALL)
        .border_style(if p_on { bdr_f } else { bdr_c });
    let p_para = Paragraph::new(Line::from(
        Span::styled(stars.clone(), if p_on { txt_f } else { txt_c })
    )).block(p_block);
    f.render_widget(p_para, chunks[idx_pwd]);
    if p_on {
        f.set_cursor(chunks[idx_pwd].x + 2 + stars.len() as u16, chunks[idx_pwd].y + 1);
    }

    // ── Error ──
    if !app.error_msg.is_empty() {
        let err = Paragraph::new(Line::from(
            Span::styled(format!("  {}", app.error_msg), err_c)
        ));
        f.render_widget(err, chunks[idx_err]);
    }

    // ── Hint ──
    let hint = Paragraph::new(Line::from(
        Span::styled("  F1:Shutdown  F2:Reboot  Tab:Focus  \u{2190}\u{2192}:Session  Enter:Next  Ctrl+U:Clear", hint_c)
    ));
    f.render_widget(hint, chunks[idx_hint]);
}
