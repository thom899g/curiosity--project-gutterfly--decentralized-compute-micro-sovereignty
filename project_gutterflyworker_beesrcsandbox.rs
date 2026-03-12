use std::error::Error;
use wasmtime::{Engine, Store, Module, Linker};
use wasmtime_wasi::sync::WasiCtxBuilder;
use std::time::{SystemTime, UNIX_EPOCH};
use tracing::{info, warn, error};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct JobResult {
    pub job_id: String,
    pub output: Vec<u8>,
    pub execution_time_ms: u128,
    pub success: bool,
    pub error_message: Option<String>,
}

pub struct SandboxManager {
    engine: Engine,
}

impl SandboxManager {
    pub async fn new() -> Result<Self, Box<dyn Error>> {
        let config = wasmtime::Config::new()
            .wasm_multi_memory(true)
            .wasm_memory64(false)
            .consume_fuel(true)
            .strategy(wasmtime::Strategy::Cranelift);
            
        let engine = Engine::new(&config)?;
        
        info!("✅ WASM sandbox engine initialized");
        Ok(SandboxManager { engine })
    }
    
    pub async fn execute_wasm(&self, wasm_bytes: &[u8], input: &[u8]) -> Result<JobResult, Box<dyn Error>> {
        let start_time = SystemTime::now();
        
        // Prepare WASI context with strict limitations
        let wasi = WasiCtxBuilder::new()
            .inherit_stdin(false)
            .inherit_stdout(false)
            .inherit_stderr(false)
            .build();
            
        let mut store = Store::new(&self.engine, wasi);
        
        // Set fuel limit (computational budget)
        store.add_fuel(1_000_000)?;
        
        // Compile module
        let module = Module::new(&self.engine, wasm_bytes)?;
        
        // Link with WASI
        let mut linker = Linker::new(&self.engine);
        wasmtime_wasi::sync::add_to_linker(&mut linker, |s| s)?;
        
        // Instantiate with strict resource limits
        let instance = linker.instantiate(&mut store, &module)?;
        
        // Find the "compute" function
        let compute_func = instance.get_typed_func::<(i32, i32), i32>(&mut store, "compute")?;
        
        // Allocate input in memory
        let memory = instance.get_memory(&mut store, "memory")
            .ok_or("No memory export found")?;
            
        let input_len = input.len() as i32;
        let input_ptr = 0; // We'll allocate at the start
        
        // Write input to memory
        memory.write(&mut store, input_ptr as usize, input)?;
        
        // Execute with fuel monitoring
        match compute_func.call(&mut store, (input_ptr, input_len)) {
            Ok(output_ptr) => {
                // Read output from memory
                let output_size = memory.data_size(&store) as i32;
                let mut output_buffer = vec![0; (output_size - output_ptr) as usize];
                memory.read(&store, output_ptr as usize, &mut output_buffer)?;
                
                let elapsed = start_time.elapsed().unwrap_or_default().as_millis();
                
                Ok(JobResult {
                    job_id: "".to_string(), // To be filled by caller
                    output: output_buffer,
                    execution_time_ms: elapsed,
                    success: true,
                    error_message: None,
                })
            }
            Err(e) => {
                let elapsed = start_time.elapsed().unwrap_or_default().as_millis();
                error!("WASM execution failed: {}", e);
                
                Ok(JobResult {
                    job_id: "".to_string(),
                    output: vec![],
                    execution_time_ms: elapsed,
                    success: false,
                    error_message: Some(e.to_string()),
                })
            }
        }
    }
}