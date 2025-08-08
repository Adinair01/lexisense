import os
import logging
import numpy as np
import faiss
from typing import List, Tuple, Optional
import json
import pickle
from openai import OpenAI

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Handles embedding generation and vector similarity search"""
    
    def __init__(self):
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found in environment variables")
        
        self.client = OpenAI(api_key=self.openai_api_key) if self.openai_api_key else None
        self.embedding_model = "text-embedding-3-large"
        self.embedding_dimension = 3072  # text-embedding-3-large dimension
        self.index = None
        self.chunk_ids = []
        self.index_file = "faiss_index.bin"
        self.metadata_file = "chunk_metadata.pkl"
        
        self._load_or_create_index()
    
    def _load_or_create_index(self):
        """Load existing FAISS index or create new one"""
        try:
            if os.path.exists(self.index_file) and os.path.exists(self.metadata_file):
                logger.info("Loading existing FAISS index")
                self.index = faiss.read_index(self.index_file)
                with open(self.metadata_file, 'rb') as f:
                    self.chunk_ids = pickle.load(f)
                logger.info(f"Loaded index with {self.index.ntotal} vectors")
            else:
                logger.info("Creating new FAISS index")
                self._create_new_index()
        except Exception as e:
            logger.error(f"Error loading FAISS index: {str(e)}")
            self._create_new_index()
    
    def _create_new_index(self):
        """Create a new FAISS index"""
        self.index = faiss.IndexFlatIP(self.embedding_dimension)  # Inner product for cosine similarity
        self.chunk_ids = []
        self._save_index()
    
    def _save_index(self):
        """Save FAISS index and metadata to disk"""
        try:
            faiss.write_index(self.index, self.index_file)
            with open(self.metadata_file, 'wb') as f:
                pickle.dump(self.chunk_ids, f)
            logger.debug("FAISS index saved successfully")
        except Exception as e:
            logger.error(f"Error saving FAISS index: {str(e)}")
    
    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for a single text"""
        if not self.client:
            logger.error("OpenAI client not initialized")
            return None
        
        try:
            # Clean and truncate text if too long
            text = text.strip()
            if len(text) > 8000:  # Conservative limit for embedding model
                text = text[:8000]
            
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            embedding = np.array(response.data[0].embedding, dtype=np.float32)
            
            # Normalize for cosine similarity
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            
            return embedding
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error generating embedding: {error_message}")
            if "insufficient_quota" in error_message or "429" in error_message:
                logger.warning("OpenAI API quota exceeded - embeddings temporarily unavailable")
            return None
    
    def add_chunk_embeddings(self, chunks: List[Tuple[int, str]]) -> bool:
        """Add embeddings for document chunks to the index"""
        try:
            embeddings = []
            chunk_ids_to_add = []
            
            for chunk_id, chunk_text in chunks:
                embedding = self.generate_embedding(chunk_text)
                if embedding is not None:
                    embeddings.append(embedding)
                    chunk_ids_to_add.append(chunk_id)
                else:
                    logger.warning(f"Failed to generate embedding for chunk {chunk_id}")
            
            if embeddings:
                embeddings_array = np.vstack(embeddings).astype(np.float32)
                self.index.add(embeddings_array)
                self.chunk_ids.extend(chunk_ids_to_add)
                self._save_index()
                
                logger.info(f"Added {len(embeddings)} chunk embeddings to index")
                return True
            else:
                logger.warning("No embeddings generated for chunks")
                return False
                
        except Exception as e:
            logger.error(f"Error adding chunk embeddings: {str(e)}")
            return False
    
    def search_similar_chunks(self, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
        """Search for similar chunks using the query"""
        if not self.client:
            logger.error("OpenAI client not initialized")
            return []
        
        try:
            # Generate query embedding
            query_embedding = self.generate_embedding(query)
            if query_embedding is None:
                logger.error("Failed to generate query embedding")
                return []
            
            # Perform similarity search
            if self.index.ntotal == 0:
                logger.warning("No chunks in the index")
                return []
            
            # Search for similar vectors
            scores, indices = self.index.search(
                query_embedding.reshape(1, -1).astype(np.float32), 
                min(top_k, self.index.ntotal)
            )
            
            # Return chunk IDs and similarity scores
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx != -1 and idx < len(self.chunk_ids):  # Valid index
                    chunk_id = self.chunk_ids[idx]
                    results.append((chunk_id, float(score)))
            
            logger.debug(f"Found {len(results)} similar chunks for query")
            return results
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error searching similar chunks: {error_message}")
            if "insufficient_quota" in error_message or "429" in error_message:
                logger.warning("OpenAI API quota exceeded - search temporarily unavailable")
            return []
    
    def remove_document_embeddings(self, document_id: int) -> bool:
        """Remove embeddings for a specific document (rebuilds index)"""
        try:
            from models import DocumentChunk
            
            # Get chunk IDs for this document
            document_chunks = DocumentChunk.query.filter_by(document_id=document_id).all()
            chunk_ids_to_remove = {chunk.id for chunk in document_chunks}
            
            if not chunk_ids_to_remove:
                return True
            
            # Rebuild index without the removed chunks
            remaining_chunks = []
            for i, chunk_id in enumerate(self.chunk_ids):
                if chunk_id not in chunk_ids_to_remove:
                    # Get the embedding vector
                    vector = self.index.reconstruct(i)
                    remaining_chunks.append((chunk_id, vector))
            
            # Create new index
            self._create_new_index()
            
            if remaining_chunks:
                embeddings = np.vstack([chunk[1] for chunk in remaining_chunks]).astype(np.float32)
                chunk_ids = [chunk[0] for chunk in remaining_chunks]
                
                self.index.add(embeddings)
                self.chunk_ids = chunk_ids
                self._save_index()
            
            logger.info(f"Removed embeddings for document {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error removing document embeddings: {str(e)}")
            return False
    
    def get_index_stats(self) -> dict:
        """Get statistics about the current index"""
        return {
            "total_vectors": self.index.ntotal if self.index else 0,
            "dimension": self.embedding_dimension,
            "total_chunks": len(self.chunk_ids)
        }
