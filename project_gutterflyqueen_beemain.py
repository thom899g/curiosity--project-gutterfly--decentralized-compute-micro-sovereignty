#!/usr/bin/env python3
"""
QUEEN BEE - GUTTERFLY Strategic Controller
Main orchestrator for decentralized compute sovereignty
"""

import asyncio
import logging
import signal
import sys
from typing import Optional, Dict, Any
from dataclasses import dataclass

from firebase_client import FirebaseClient
from marketplace.vastai import VastAIAdapter
from marketplace.akash import AkashAdapter
from financial_engine import FinancialEngine
from worker_orchestrator import WorkerOrchestrator
from config import Config, load_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('queen_bee.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class SystemHealth:
    """System health status"""
    workers_active: int = 0
    workers_total: int = 0
    marketplace_connections: int = 0
    treasury_balance_usd: float = 0.0
    last_job_completed: Optional[str] = None
    uptime_seconds: float = 0.0
    error_count: int = 0

class QueenBee:
    """Main orchestrator for GUTTERFLY system"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config: Config = load_config(config_path)
        self.health = SystemHealth()
        self.shutdown_flag = False
        
        # Initialize components
        self.firebase_client: Optional[FirebaseClient] = None
        self.vastai_adapter: Optional[VastAIAdapter] = None
        self.akash_adapter: Optional[AkashAdapter] = None
        self.financial_engine: Optional[FinancialEngine] = None
        self.worker_orchestrator: Optional[WorkerOrchestrator] = None
        
        # Signal handling
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
    async def initialize(self) -> bool:
        """Initialize all system components"""
        try:
            logger.info("👑 QUEEN BEE Initializing GUTTERFLY System...")
            
            # 1. Firebase - CRITICAL STATE STORE
            self.firebase_client = FirebaseClient(self.config.firebase_credentials)
            await self.firebase_client.initialize()
            
            # 2. Marketplace adapters
            if self.config.marketplaces.vastai.enabled:
                self.vastai_adapter = VastAIAdapter(self.config.marketplaces.vastai.api_key)
                await self.vastai_adapter.test_connection()
                
            if self.config.marketplaces.akash.enabled:
                self.akash_adapter = AkashAdapter(
                    self.config.marketplaces.akash.wallet_mnemonic,
                    self.config.marketplaces.akash.network
                )
                await self.akash_adapter.test_connection()
            
            # 3. Financial engine
            self.financial_engine = FinancialEngine(
                firebase_client=self.firebase_client,
                eth_rpc_url=self.config.blockchain.eth_rpc_url,
                private_key=self.config.wallet.private_key
            )
            
            # 4. Worker orchestrator
            self.worker_orchestrator = WorkerOrchestrator(
                firebase_client=self.firebase_client,
                worker_config=self.config.workers
            )
            await self.worker_orchestrator.discover_workers()
            
            logger.info("✅ QUEEN BEE Initialization complete")
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}", exc_info=True)
            return False
    
    async def run_main_loop(self):
        """Main operational loop"""
        logger.info("🌀 Starting main operational loop")
        
        while not self.shutdown_flag:
            try:
                # Phase 1: Check for new jobs
                await self.check_marketplaces()
                
                # Phase 2: Process active jobs
                await self.process_active_jobs()
                
                # Phase 3: Financial operations
                await self.execute_financial_operations()
                
                # Phase 4: System maintenance
                await self.perform_maintenance()
                
                # Phase 5: Update health status
                await self.update_health_status()
                
                # Wait for next cycle
                await asyncio.sleep(self.config.main_loop_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}", exc_info=True)
                self.health.error_count += 1
                await asyncio.sleep(10)  # Backoff on error
    
    async def check_marketplaces(self):
        """Check all marketplaces for new job opportunities"""
        try:
            if self.vastai_adapter:
                jobs = await self.vastai_adapter.fetch_available_jobs()
                for job in jobs:
                    if self._should_accept_job(job):
                        await self._accept_job(job, 'vastai')
            
            if self.akash_adapter:
                jobs = await self.akash_adapter.fetch_available_jobs()
                for job in jobs:
                    if self._should_accept_job(job):
                        await self._accept_job(job, 'akash')
                        
        except Exception as e:
            logger.error(f"Error checking marketplaces: {e}")
    
    def _should_accept_job(self, job: Dict[str, Any]) -> bool:
        """Determine if we should accept a job based on strategy"""
        # Minimum profitability check
        if job.get('rate_usd_per_hour', 0) < self.config.pricing.minimum_rate_usd:
            return False
        
        # Resource compatibility check
        required_gpu = job.get('gpu_required', False)
        if required_gpu and not self.config.workers.has_gpu_capacity:
            return False
        
        # Trust score check (for P2P jobs)
        client_score = job.get('client_trust_score', 0)
        if client_score < self.config.security.minimum_trust_score:
            return False
            
        return True
    
    async def _accept