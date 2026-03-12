use std::error::Error;
use tokio::sync::Mutex;
use std::sync::Arc;
use tracing::{info, error, warn};
use crate::grpc_server::WorkerService;
use crate::sandbox::SandboxManager;
use crate::crypto::CryptoEngine;

mod grpc_server;
mod sandbox;
mod crypto;
mod metrics;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    // Initialize logging
    tracing_subscriber::fmt::init();
    
    info!("🚀 GUTTERFLY Worker Bee v0.1.0 starting...");
    
    // Initialize cryptographic engine
    let crypto_engine = Arc::new(Mutex::new(CryptoEngine::new().await?));
    info!("✅ Cryptographic engine initialized");
    
    // Initialize sandbox manager
    let sandbox_manager = Arc::new(Mutex::new(SandboxManager::new().await?));
    info!("✅ Sandbox manager initialized");
    
    // Initialize metrics server
    let metrics_handle = metrics::start_metrics_server("0.0.0.0:9090").await?;
    info!("✅ Metrics server started on port 9090");
    
    // Start gRPC server
    let worker_service = WorkerService::new(
        crypto_engine.clone(),
        sandbox_manager.clone()
    );
    
    info!("📡 Starting gRPC server on 0.0.0.0:50051");
    grpc_server::start_server(worker_service).await?;
    
    // Keep main running
    tokio::select! {
        _ = metrics_handle => {},
        _ = tokio::signal::ctrl_c() => {
            info!("🛑 Received shutdown signal");
        }
    }
    
    info!("👋 Worker Bee shutting down gracefully");
    Ok(())
}