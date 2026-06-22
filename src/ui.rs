use crate::app::{App, Focus, PluginPosition};
use crate::config;
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Paragraph},
    Frame,
};

const SQ: &str = "▪";
const ARROW_L: &str = "◀";
const ARROW_R: &str = "▶";
const ICON_USER: &str = "👤";
const ICON_KEY: &str = "🔑";
const ICON_SESSION: &str = "⊞";

/// 绘制带 rounded 边框的面板
fn rounded_block<'a>(title: &str, style: Style) -> Block<'a> {
    let border_set = ratatui::widgets::Borders::ALL;
    Block::default()
        .title(format!(" {} ", title))
        .borders(border_set)
        .border_style(style)
        .border_type(BorderType::Rounded)
}

/// 绘制背景填充
fn render_background(f: &mut Frame, area: Rect, pattern: &str) {
    if pattern.is_empty() || pattern == "none" {
        return;
    }
    let bg_style = config::parse_style(pattern);
    // Use a subtle dotted pattern
    for y in area.top()..area.bottom() {
        for x in area.left()..area.right() {
            if (x + y) % 3 == 0 {
                let c = ratatui::widgets::Paragraph::new("·")
                    .style(bg_style);
                f.render_widget(c, Rect::new(x, y, 1, 1));
            }
        }
    }
}

// ─── 插件渲染 ──────────────────────────────────────────

fn plugin_height(plugins: &[crate::app::PluginBlock]) -> usize {
    plugins.iter().map(|p| p.lines.len()).sum::<usize>() + plugins.len().saturating_sub(1) // gaps
}

/// 在指定区域渲染插件块，每个 block 之间有一个空行
fn render_plugin_block(f: &mut Frame, area: Rect, plugins: &[crate::app::PluginBlock], style: Style) -> usize {
    let mut y = area.y;
    for block in plugins {
        for line in &block.lines {
            if y >= area.bottom() {
                return y as usize;
            }
            let span = Span::styled(line.clone(), style);
            let p = Paragraph::new(Line::from(span)).alignment(Alignment::Center);
            f.render_widget(p, Rect::new(area.x, y, area.width, 1));
            y += 1;
        }
        // gap between blocks
        y += 1;
    }
    y as usize
}

// ─── 主渲染 ────────────────────────────────────────────

pub fn render(f: &mut Frame, app: &App) {
    let area = f.size();
    let th = &app.config.theme;

    // 解析所有样式
    let panel_st = config::parse_style(&th.panel_title);
    let accent_st = config::parse_style(&th.accent);
    let bdr_st = config::parse_style(&th.border);
    let bdr_f_st = config::parse_style(&th.border_focus);
    let txt_st = config::parse_style(&th.text);
    let txt_f_st = config::parse_style(&th.text_focus);
    let plug_st = config::parse_style(&th.plugin);
    let hint_st = config::parse_style(&th.hint);
    let err_st = config::parse_style(&th.error);
    let sess_st = config::parse_style(&th.session);
    let sess_f_st = config::parse_style(&th.session_focus);
    let sep_st = config::parse_style(&th.separator);
    let title_st = config::parse_style(&th.title);

    // 背景填充
    render_background(f, area, &th.background);

    // ── 自适应布局：宽屏水平分栏(≥80)，窄屏垂直堆叠 ──
    let use_horizontal = match th.layout.as_str() {
        "horizontal" => true,
        "vertical" => false,
        _ => area.width >= 80, // "auto"
    };

    // 分类插件
    let left_plugins: Vec<_> = app.plugins.iter().filter(|p| p.position == PluginPosition::Left).cloned().collect();
    let center_plugins: Vec<_> = app.plugins.iter().filter(|p| p.position == PluginPosition::Center).cloned().collect();
    let right_plugins: Vec<_> = app.plugins.iter().filter(|p| p.position == PluginPosition::Right).cloned().collect();

    if use_horizontal {
        render_horizontal(f, area, app, &RenderContext {
            panel_st, accent_st, bdr_st, bdr_f_st, txt_st, txt_f_st,
            plug_st, hint_st, err_st, sess_st, sess_f_st, sep_st, title_st,
            left_plugins: &left_plugins,
            center_plugins: &center_plugins,
            right_plugins: &right_plugins,
        });
    } else {
        render_vertical(f, area, app, &RenderContext {
            panel_st, accent_st, bdr_st, bdr_f_st, txt_st, txt_f_st,
            plug_st, hint_st, err_st, sess_st, sess_f_st, sep_st, title_st,
            left_plugins: &left_plugins,
            center_plugins: &center_plugins,
            right_plugins: &right_plugins,
        });
    }
}

struct RenderContext<'a> {
    panel_st: Style,
    accent_st: Style,
    bdr_st: Style,
    bdr_f_st: Style,
    txt_st: Style,
    txt_f_st: Style,
    plug_st: Style,
    hint_st: Style,
    err_st: Style,
    sess_st: Style,
    sess_f_st: Style,
    #[allow(dead_code)]
    sep_st: Style,
    title_st: Style,
    left_plugins: &'a [crate::app::PluginBlock],
    center_plugins: &'a [crate::app::PluginBlock],
    #[allow(dead_code)]
    right_plugins: &'a [crate::app::PluginBlock],
}

// ─── 水平布局（宽屏）── 左: branding+plugins, 右: 输入 ──

fn render_horizontal(f: &mut Frame, area: Rect, app: &App, ctx: &RenderContext) {
    // ── 外层大面板 ──
    let outer = rounded_block(&app.config.branding.title, ctx.panel_st);
    let outer_area = outer.inner(area);
    f.render_widget(outer, area);

    // 左右分栏（左 45%，右 55%）
    let h_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .horizontal_margin(1)
        .constraints([Constraint::Percentage(45), Constraint::Percentage(55)])
        .split(outer_area);

    let left_area = h_chunks[0];
    let right_area = h_chunks[1];

    // ── 左面板：branding 区域 ──
    render_branding_panel(f, left_area, app, ctx);

    // ── 右面板：登录区域 ──
    render_login_panel(f, right_area, app, ctx, false);
}

// ─── 垂直布局（窄屏）── 整体堆叠 ──

fn render_vertical(f: &mut Frame, area: Rect, app: &App, ctx: &RenderContext) {
    let outer = rounded_block(&app.config.branding.title, ctx.panel_st);
    let inner = outer.inner(area);
    f.render_widget(outer, area);

    // 先计算左边插件+右边登录需要的高度
    let branding_h = 3 + plugin_height(ctx.left_plugins) + plugin_height(ctx.center_plugins);
    let login_min_h = 12;

    let use_split = inner.height as usize > branding_h + login_min_h;

    if use_split {
        let v_chunks = Layout::default()
            .direction(Direction::Vertical)
            .horizontal_margin(1)
            .constraints([
                Constraint::Length(branding_h as u16),
                Constraint::Min(login_min_h as u16),
            ])
            .split(inner);

        render_branding_panel(f, v_chunks[0], app, ctx);
        render_login_panel(f, v_chunks[1], app, ctx, true);
    } else {
        // 太窄，紧凑布局：只显示登录
        render_minimal_login(f, inner, app, ctx);
    }
}

// ─── Branding 面板 ──────────────────────────────────────

fn render_branding_panel(f: &mut Frame, area: Rect, _app: &App, ctx: &RenderContext) {
    let branding_block = rounded_block("", ctx.bdr_st);
    let inner = branding_block.inner(area);
    f.render_widget(branding_block, area);

    // 堆叠: 居中插件 + 左插件
    let total_plugin_h = plugin_height(ctx.center_plugins) 
        + if !ctx.left_plugins.is_empty() { plugin_height(ctx.left_plugins) + 1 } else { 0 };
    let title_h = if !ctx.center_plugins.is_empty() { 0 } else { 1 };

    let total_content = total_plugin_h + title_h;
    let top_padding = if inner.height as usize > total_content {
        (inner.height as usize - total_content) / 2
    } else {
        0
    };

    let mut y = inner.y + top_padding as u16;
    let bottom = inner.bottom();

    // 居中插件（如时钟）
    if !ctx.center_plugins.is_empty() {
        y = render_plugin_block(f, Rect::new(inner.x, y, inner.width, (bottom - y) as u16), ctx.center_plugins, ctx.plug_st) as u16;
        y += 1; // gap
    } else {
        // 没有插件时显示问候语
        if y < bottom {
            let greeting = format!(" {} Welcome ", ICON_USER);
            let p = Paragraph::new(Line::from(Span::styled(greeting, ctx.title_st)))
                .alignment(Alignment::Center);
            f.render_widget(p, Rect::new(inner.x, y, inner.width, 1));
            y += 2;
        }
    }

    // 左插件（如 sysinfo）放在底部
    if !ctx.left_plugins.is_empty() && y < bottom {
        render_plugin_block(f, Rect::new(inner.x, y, inner.width, (bottom - y) as u16), ctx.left_plugins, ctx.hint_st);
    }
}

// ─── 登录面板 ──────────────────────────────────────────

fn render_login_panel(f: &mut Frame, area: Rect, app: &App, ctx: &RenderContext, is_narrow: bool) {
    let login_block = rounded_block("Login", ctx.accent_st);
    let inner = login_block.inner(area);
    f.render_widget(login_block, area);

    if inner.height < 10 {
        // 空间不够，走极简模式
        render_minimal_login(f, area, app, ctx);
        return;
    }

    let margin = if is_narrow { 1 } else { 2 };
    let content_area = Rect::new(
        inner.x + margin,
        inner.y + 1,
        inner.width.saturating_sub(margin * 2),
        inner.height.saturating_sub(2),
    );

    // 内容从上到下：Session → Username → Password → Error → Hint
    let mut y = content_area.y;

    // ── Session 选择器（增强版，带箭头和徽章）──
    let session = app.current_session();
    let s_on = app.focus == Focus::Session;
    let s_sty = if s_on { ctx.sess_f_st } else { ctx.sess_st };

    let session_text = if s_on {
        format!(" {} {} {} {} {}  ", ARROW_L, ICON_SESSION, session.name, ARROW_R, SQ)
    } else {
        format!("   {} {}   ", ICON_SESSION, session.name)
    };

    let session_block = if s_on {
        Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(ctx.accent_st)
            .title(" Session ")
            .title_style(ctx.accent_st)
    } else {
        Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(ctx.bdr_st)
    };

    let session_para = Paragraph::new(Line::from(Span::styled(session_text, s_sty)))
        .block(session_block)
        .alignment(Alignment::Center);

    f.render_widget(session_para, Rect::new(content_area.x, y, content_area.width, 3));
    y += 4;

    // ── Username 输入框 ──
    let u_on = app.focus == Focus::Username;
    let u_bdr = if u_on { ctx.bdr_f_st } else { ctx.bdr_st };
    let u_txt = if u_on { ctx.txt_f_st } else { ctx.txt_st };

    let display_user = if app.username.is_empty() && !u_on {
        "(username)".to_string()
    } else {
        app.username.clone()
    };

    let u_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(u_bdr)
        .title(format!(" {} Login name ", ICON_USER))
        .title_style(if u_on { ctx.accent_st } else { ctx.bdr_st });

    let cursor_char = if u_on { "▌" } else { "" };
    let u_text = format!(" {} {}", display_user, cursor_char);
    let u_para = Paragraph::new(Line::from(Span::styled(u_text, u_txt)))
        .block(u_block);

    f.render_widget(u_para, Rect::new(content_area.x, y, content_area.width, 3));
    if u_on {
        // Better cursor position for wide chars
        f.set_cursor(
            content_area.x + 2 + display_user.chars().count() as u16,
            y + 1,
        );
    }
    y += 4;

    // ── Password 输入框 ──
    let p_on = app.focus == Focus::Password;
    let p_bdr = if p_on { ctx.bdr_f_st } else { ctx.bdr_st };
    let p_txt = if p_on { ctx.txt_f_st } else { ctx.txt_st };

    let display_pwd = if app.password.is_empty() && !p_on {
        "(password)".to_string()
    } else if app.password_visible {
        app.password.clone()
    } else {
        app.password.chars().map(|_| '●').collect::<String>()
    };

    let vis_indicator = if app.password_visible { " 👁 " } else { "" };

    let p_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(p_bdr)
        .title(format!(" {} Password {}", ICON_KEY, vis_indicator))
        .title_style(if p_on { ctx.accent_st } else { ctx.bdr_st });

    let cursor_char = if p_on { "▌" } else { "" };
    let p_text = format!(" {} {}", display_pwd, cursor_char);
    let p_para = Paragraph::new(Line::from(Span::styled(p_text, p_txt)))
        .block(p_block);

    f.render_widget(p_para, Rect::new(content_area.x, y, content_area.width, 3));
    if p_on {
        let vis_len = if app.password_visible {
            app.password.chars().count()
        } else {
            app.password.len() // each char → ● (1 wide)
        };
        f.set_cursor(
            content_area.x + 2 + vis_len as u16,
            y + 1,
        );
    }
    y += 4;

    // ── Error ──
    if !app.error_msg.is_empty() && y < content_area.bottom() {
        let err_text = format!(" ⚠ {}", app.error_msg);
        let err = Paragraph::new(Line::from(Span::styled(err_text, ctx.err_st)))
            .alignment(Alignment::Center);
        f.render_widget(err, Rect::new(content_area.x, y, content_area.width, 1));
        y += 1;
    }

    // ── Hint ──
    if y + 1 < content_area.bottom() {
        // Use bottom of panel for hint
        let hint_y = area.y + area.height.saturating_sub(2);
        let hint_text = if is_narrow {
            "Tab:focus ←→:session Enter:next Esc:back"
        } else {
            "Tab/↓:focus  ←→:session  Enter:next  Esc:back  Ctrl+T:reveal  F1:off  F2:reboot  q:quit"
        };
        let hint = Paragraph::new(Line::from(Span::styled(hint_text, ctx.hint_st)))
            .alignment(Alignment::Center);
        f.render_widget(hint, Rect::new(area.x + 2, hint_y, area.width.saturating_sub(4), 1));
    }
}

// ─── 极简模式（屏幕太小） ─────────────────────────────

fn render_minimal_login(f: &mut Frame, area: Rect, app: &App, ctx: &RenderContext) {
    let v_chunks = Layout::default()
        .direction(Direction::Vertical)
        .horizontal_margin(2)
        .constraints([
            Constraint::Length(1), // session
            Constraint::Length(1), // username
            Constraint::Length(1), // password
            Constraint::Length(1), // error/hint
        ])
        .split(area);

    // Session
    let s_on = app.focus == Focus::Session;
    let s_sty = if s_on { ctx.sess_f_st } else { ctx.sess_st };
    let s_text = format!(" [{}] ", app.current_session().name);
    let s = Paragraph::new(Line::from(Span::styled(s_text, s_sty))).alignment(Alignment::Center);
    f.render_widget(s, v_chunks[0]);

    // Username
    let u_on = app.focus == Focus::Username;
    let u_sty = if u_on { ctx.txt_f_st } else { ctx.txt_st };
    let u_display = if app.username.is_empty() { "(user)" } else { &app.username };
    let u = Paragraph::new(Line::from(Span::styled(format!("login: {}", u_display), u_sty)));
    f.render_widget(u, v_chunks[1]);
    if u_on {
        f.set_cursor(v_chunks[1].x + 7 + u_display.chars().count() as u16, v_chunks[1].y);
    }

    // Password
    let p_on = app.focus == Focus::Password;
    let p_sty = if p_on { ctx.txt_f_st } else { ctx.txt_st };
    let p_display = if app.password_visible { app.password.clone() } else { app.password.chars().map(|_| '*').collect::<String>() };
    let p = Paragraph::new(Line::from(Span::styled(format!("pass: {}", p_display), p_sty)));
    f.render_widget(p, v_chunks[2]);
    if p_on {
        f.set_cursor(v_chunks[2].x + 6 + p_display.len() as u16, v_chunks[2].y);
    }

    // Error/Hint
    let bottom = if !app.error_msg.is_empty() {
        Span::styled(app.error_msg.clone(), ctx.err_st)
    } else {
        Span::styled("Ctrl+T:toggle pass | F1:off F2:reboot q:quit", ctx.hint_st)
    };
    let h = Paragraph::new(Line::from(bottom)).alignment(Alignment::Center);
    f.render_widget(h, v_chunks[3]);
}
