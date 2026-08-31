// Evita abrir um console no build de release do Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    usage_buddies_win::run();
}
