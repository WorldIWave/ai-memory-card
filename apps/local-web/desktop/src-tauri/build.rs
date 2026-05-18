//! Input: Cargo 构建环境  |  Output: Tauri 所需的平台资源和清单（副作用）
//! Role: Tauri 构建脚本，调用 tauri_build::build() 完成图标、权限清单等预处理
//! Note: 必须保留此文件，否则 Tauri 构建流程无法生成平台相关资源
//! Usage: Cargo 在编译 tauri 目标前自动执行，无需手动调用
fn main() {
    tauri_build::build()
}
