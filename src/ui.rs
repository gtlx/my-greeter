use crate::app::{App, Focus};
use crate::config;
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

pub fn render(f: &mut Frame, app: &App) {
    let area = f.size();

    // ── 动态 constraints ──
    let n = app.plugin_lines.len();
    let mut c = Vec::new();
    c.push(Constraint::Min(0));          // 0: 上半弹性
    c.push(Constraint::Length(1));       // 1: title
    c.push(Constraint::Length(1));       // 2: separator
    for _ in 0..n {
        c.push(Constraint::Length(1));   // 3..n+2: plugins
    }
    c.push(Constraint::Length(1));       // n+3: gap
    c.push(Constraint::Length(1));       // n+4: session
    c.push(Constraint::Length(1));       // n+5: gap
    c.push(Constraint::Length(3));       // n+6: username
    c.push(Constraint::Length(1));       // n+7: gap
    c.push(Constraint::Length(3));       // n+8: password
    c.push(Constraint::Length(1));       // n+9: gap/error
    c.push(Constraint::Length(1));       // n+10: hint
    c.push(Constraint::Min(0));          // n+11: 下半弹性

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .horizontal_margin(2)
        .vertical_margin(0)
        .constraints(c)
        .split(area);

    let idx_title = 1;
    let idx_sep = 2;
    let idx_plugin_start = 3;
    let idx_session = n + 4;
    let idx_user = n + 6;
    let idx_pwd = n + 8;
    let idx_err = n + 9;
    let idx_hint = n + 10;

    // ── 从配置读取主题 ──
    let th = &app.config.theme;
    let title_st = config::parse_style(&th.title);
    let sep_st = config::parse_style(&th.separator);
    let bdr_st = config::parse_style(&th.border);
    let bdr_f_st = config::parse_style(&th.border_focus);
    let txt_st = config::parse_style(&th.text);
    let txt_f_st = config::parse_style(&th.text_focus);
    let plug_st = config::parse_style(&th.plugin);
    let hint_st = config::parse_style(&th.hint);
    let err_st = config::parse_style(&th.error);
    let sess_st = config::parse_style(&th.session);
    let sess_f_st = config::parse_style(&th.session_focus);

    // ── Title ──
    let title = Paragraph::new(Line::from(Span::styled(
        &app.config.branding.title, title_st
    ))).alignment(Alignment::Center);
    f.render_widget(title, chunks[idx_title]);

    // ── Separator ──
    let sep_w = chunks[idx_sep].width as usize;
    let sep = Paragraph::new(Line::from(Span::styled("─".repeat(sep_w), sep_st)));
    f.render_widget(sep, chunks[idx_sep]);

    // ── Plugins ──
    for (i, line) in app.plugin_lines.iter().enumerate() {
        let plug = Paragraph::new(Line::from(
            Span::styled(format!("  {}", line), plug_st)
        )).alignment(Alignment::Center);
        f.render_widget(plug, chunks[idx_plugin_start + i]);
    }

    // ── Session ──
    let s_sty = if app.focus == Focus::Session { sess_f_st } else { sess_st };
    let sess = Paragraph::new(Line::from(
        Span::styled(format!("  < {} >  ", app.current_session().name), s_sty)
    )).alignment(Alignment::Center);
    f.render_widget(sess, chunks[idx_session]);

    // ── Username ──
    let u_on = app.focus == Focus::Username;
    let u_bdr = if u_on { bdr_f_st } else { bdr_st };
    let u_txt = if u_on { txt_f_st } else { txt_st };
    let u_block = Block::default().title(" Login ").borders(Borders::ALL).border_style(u_bdr);
    let u_para = Paragraph::new(Line::from(Span::styled(app.username.clone(), u_txt))).block(u_block);
    f.render_widget(u_para, chunks[idx_user]);
    if u_on {
        f.set_cursor(chunks[idx_user].x + 2 + app.username.len() as u16, chunks[idx_user].y + 1);
    }

    // ── Password ──
    let p_on = app.focus == Focus::Password;
    let p_bdr = if p_on { bdr_f_st } else { bdr_st };
    let p_txt = if p_on { txt_f_st } else { txt_st };
    let stars: String = app.password.chars().map(|_| '*').collect();
    let p_block = Block::default().title(" Password ").borders(Borders::ALL).border_style(p_bdr);
    let p_para = Paragraph::new(Line::from(Span::styled(stars.clone(), p_txt))).block(p_block);
    f.render_widget(p_para, chunks[idx_pwd]);
    if p_on {
        f.set_cursor(chunks[idx_pwd].x + 2 + stars.len() as u16, chunks[idx_pwd].y + 1);
    }

    // ── Error ──
    if !app.error_msg.is_empty() {
        let err = Paragraph::new(Line::from(Span::styled(
            format!("  {}", app.error_msg), err_st
        )));
        f.render_widget(err, chunks[idx_err]);
    }

    // ── Hint ──
    let hint = Paragraph::new(Line::from(Span::styled(
        "  F1:Shutdown  F2:Reboot  Tab:Focus  \u{2190}\u{2192}:Session  Enter:Next  Ctrl+U:Clear",
        hint_st,
    )));
    f.render_widget(hint, chunks[idx_hint]);
}
