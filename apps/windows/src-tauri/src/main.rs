// Programa do Windows: abre o sistema da Pronutre em janela própria (sem barra de navegador).
// O conteúdo vem do servidor, então cada atualização do sistema chega sem reinstalar.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("não foi possível abrir o sistema");
}
