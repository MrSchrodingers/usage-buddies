use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager,
};

const MAX_DATA_SIZE: u64 = 1_048_576; // 1 MB — teto defensivo antes de ler o arquivo

// Tamanhos das duas janelas (mantidos em sync com tauri.conf.json).
const PANEL_W: f64 = 360.0;
const PANEL_H: f64 = 660.0;
const PILL_W: f64 = 190.0;
const PILL_H: f64 = 60.0;

/// Lê ~/.claude/widget-data.json e devolve o conteúdo como string.
/// Valida tamanho e JSON antes de entregar pro WebView (evita exaustão de
/// memória e injeção de conteúdo malformado).
#[tauri::command]
fn get_widget_data() -> Result<String, String> {
    let path = dirs::home_dir()
        .ok_or_else(|| "não foi possível resolver o diretório home".to_string())?
        .join(".claude")
        .join("widget-data.json");

    let meta = std::fs::metadata(&path)
        .map_err(|e| format!("widget-data.json indisponível: {e}"))?;
    if meta.len() > MAX_DATA_SIZE {
        return Err(format!("widget-data.json grande demais ({} bytes)", meta.len()));
    }

    let contents =
        std::fs::read_to_string(&path).map_err(|e| format!("erro ao ler widget-data.json: {e}"))?;
    serde_json::from_str::<serde_json::Value>(&contents)
        .map_err(|e| format!("widget-data.json com JSON inválido: {e}"))?;
    Ok(contents)
}

/// Posiciona a janela no canto inferior direito, com folga para a taskbar.
fn position_corner(win: &tauri::WebviewWindow, w: f64, h: f64) {
    if let Ok(Some(monitor)) = win.current_monitor() {
        let scale = monitor.scale_factor();
        let ms = monitor.size().to_logical::<f64>(scale);
        let (margin, taskbar) = (12.0_f64, 52.0_f64);
        let x = (ms.width - w - margin).max(0.0);
        let y = (ms.height - h - taskbar).max(0.0);
        let _ = win.set_position(tauri::LogicalPosition::new(x, y));
    }
}

/// Expande: esconde a pílula e mostra o painel completo no canto.
fn expand_to_panel(app: &AppHandle) {
    if let Some(pill) = app.get_webview_window("pill") {
        let _ = pill.hide();
    }
    if let Some(panel) = app.get_webview_window("popup") {
        position_corner(&panel, PANEL_W, PANEL_H);
        let _ = panel.show();
        let _ = panel.set_focus();
    }
}

/// Colapsa: esconde o painel e volta a pílula pro canto.
fn collapse_to_pill(app: &AppHandle) {
    if let Some(panel) = app.get_webview_window("popup") {
        let _ = panel.hide();
    }
    if let Some(pill) = app.get_webview_window("pill") {
        position_corner(&pill, PILL_W, PILL_H);
        let _ = pill.show();
    }
}

#[tauri::command]
fn open_panel(app: AppHandle) {
    expand_to_panel(&app);
}

#[tauri::command]
fn collapse_panel(app: AppHandle) {
    collapse_to_pill(&app);
}

/// Bandeja: clique esquerdo alterna painel/pílula; clique direito → "Sair".
/// (A pílula é o ponto de acesso principal; a bandeja é secundária.)
fn create_tray(app: &AppHandle) -> tauri::Result<()> {
    let icon = app
        .default_window_icon()
        .cloned()
        .expect("ícone padrão precisa estar definido em bundle.icon (tauri.conf.json)");

    let quit_item = MenuItem::with_id(app, "quit", "Sair", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&quit_item])?;

    TrayIconBuilder::with_id("main")
        .icon(icon)
        .tooltip("Usage Buddies")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| {
            if event.id.as_ref() == "quit" {
                app.exit(0);
            }
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                let panel_open = app
                    .get_webview_window("popup")
                    .and_then(|w| w.is_visible().ok())
                    .unwrap_or(false);
                if panel_open {
                    collapse_to_pill(app);
                } else {
                    expand_to_panel(app);
                }
            }
        })
        .build(app)?;

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            get_widget_data,
            open_panel,
            collapse_panel
        ])
        .setup(|app| {
            create_tray(app.handle())?;

            // Painel: fechar (Alt+F4) ou perder o foco (clicar fora) → colapsa pra pílula.
            if let Some(panel) = app.get_webview_window("popup") {
                let app_h = app.handle().clone();
                panel.on_window_event(move |event| match event {
                    tauri::WindowEvent::CloseRequested { api, .. } => {
                        api.prevent_close();
                        collapse_to_pill(&app_h);
                    }
                    tauri::WindowEvent::Focused(false) => {
                        // Só colapsa se o painel ainda estiver aberto (evita recursão no hide).
                        let visible = app_h
                            .get_webview_window("popup")
                            .and_then(|w| w.is_visible().ok())
                            .unwrap_or(false);
                        if visible {
                            collapse_to_pill(&app_h);
                        }
                    }
                    _ => {}
                });
            }

            // Estado inicial = pílula no canto (o painel abre no clique).
            if let Some(pill) = app.get_webview_window("pill") {
                position_corner(&pill, PILL_W, PILL_H);
                let _ = pill.show();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o app Tauri");
}
