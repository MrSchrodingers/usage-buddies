use tauri::{
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, Runtime,
};

pub fn create_tray<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let icon = app
        .default_window_icon()
        .cloned()
        .expect("default window icon must be set in tauri.conf.json");

    TrayIconBuilder::with_id("main-tray")
        .icon(icon)
        .tooltip("Usage Buddies")
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                rect,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("popup") {
                    if window.is_visible().unwrap_or(false) {
                        let _ = window.hide();
                    } else {
                        let scale = window.scale_factor().unwrap_or(1.0);
                        let win_width = 400.0;
                        let win_height = 900.0;

                        let pos = rect.position.to_logical::<f64>(scale);
                        let tray_size = rect.size.to_logical::<f64>(scale);

                        let screen_height = window
                            .current_monitor()
                            .ok()
                            .flatten()
                            .map(|m| {
                                let phys = m.size();
                                phys.height as f64 / scale
                            })
                            .unwrap_or(1080.0);

                        let x = pos.x - (win_width / 2.0);
                        let y = if pos.y < screen_height / 2.0 {
                            pos.y + tray_size.height
                        } else {
                            pos.y - win_height
                        };

                        let _ = window.set_position(tauri::LogicalPosition::new(
                            x.max(0.0),
                            y.max(0.0),
                        ));
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
            }
        })
        .build(app)?;

    Ok(())
}
