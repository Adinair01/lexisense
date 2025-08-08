import os
import logging
import numpy as np
import faiss
from typing import List, Tuple, Optional
import json
import pickle
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Handles text-based analysis with Gemini (no embeddings)"""
    
    def __init__(self):
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if not self.gemini_api_key:
            logger.warning("GEMINI_API_KEY not found in environment variables")
        
        self.client = genai.Client(api_key=self.gemini_api_key) if self.gemini_api_key else None
        # Gemini doesn't provide embeddings, so we'll use text-based analysis
        self.embedding_dimension = 768  # Standard dimension for text analysis
        self.index = None
        self.chunk_ids = []
        self.index_file = "faiss_index.bin"
        self.metadata_file = "chunk_metadata.pkl"
        
        # For now, disable FAISS and use text-based search
        self._create_empty_index()
    
    def _create_empty_index(self):
        """Create empty index structure for Gemini-based analysis"""
        try:
            logger.info("Initializing Gemini-based analysis system")
            self.index = faiss.IndexFlatIP(self.embedding_dimension)
            self.chunk_ids = []
            logger.info("Gemini analysis system ready")
        except Exception as e:
            logger.error(f"Error initializing Gemini system: {str(e)}")
            self.index = None
            self.chunk_ids = []
    
    def _create_new_index(self):
        """Create a new empty index"""
        self._create_empty_index()
    
    def _save_index(self):
        """Save index metadata to disk"""
        try:
            # Only save metadata since we're not using actual embeddings
            with open(self.metadata_file, 'wb') as f:
                pickle.dump(self.chunk_ids, f)
            logger.debug("Chunk metadata saved successfully")
        except Exception as e:
            logger.error(f"Error saving metadata: {str(e)}")
    
    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate text-based analysis score (fallback for embeddings)"""
        if not self.client:
            logger.debug("Gemini client not initialized - using text analysis")
            return None
        
        try:
            # For Gemini, we'll rely on text-based search instead of embeddings
            # Return None to trigger fallback text search
            logger.debug("Using text-based analysis instead of embeddings")
            return None
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error in text analysis: {error_message}")
            return None
    
    def add_chunk_embeddings(self, chunks: List[Tuple[int, str]]) -> bool:
        """Store chunk information for text-based analysis"""
        try:
            # Store chunk IDs for reference (no actual embeddings with Gemini)
            chunk_ids_to_add = []
            
            for chunk_id, chunk_text in chunks:
                chunk_ids_to_add.append(chunk_id)
                logger.debug(f"Registered chunk {chunk_id} for text-based search")
            
            if chunk_ids_to_add:
                self.chunk_ids.extend(chunk_ids_to_add)
                logger.info(f"Registered {len(chunk_ids_to_add)} chunks for Gemini-based analysis")
                return True
            else:
                logger.warning("No chunks to register")
                return False
                
        except Exception as e:
            logger.error(f"Error registering chunks: {str(e)}")
            return False
    
    def search_similar_chunks(self, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
        """Return empty to trigger text-based search in query analyzer"""
        logger.debug("Gemini embedding search not available - using text-based fallback")
        return []  # Always return empty to trigger fallback text search
    
    def remove_document_embeddings(self, document_id: int) -> bool:
        """Remove chunk references for a specific document"""
        try:
            from models import DocumentChunk
            
            # Get chunk IDs for this document
            document_chunks = DocumentChunk.query.filter_by(document_id=document_id).all()
            chunk_ids_to_remove = {chunk.id for chunk in document_chunks}
            
            if not chunk_ids_to_remove:
                return True
            
            # Remove chunk IDs from our list
            self.chunk_ids = [chunk_id for chunk_id in self.chunk_ids if chunk_id not in chunk_ids_to_remove]
            
            logger.info(f"Removed chunk references for document {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error removing document chunks: {str(e)}")
            return False
    
    def get_index_stats(self) -> dict:
        """Get statistics about the current system"""
        return {
            "total_vectors": 0,  # No vectors with Gemini text-based analysis
            "dimension": self.embedding_dimension,
            "total_chunks": len(self.chunk_ids)
        }