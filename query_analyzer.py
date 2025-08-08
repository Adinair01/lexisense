import os
import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from openai import OpenAI
from models import DocumentChunk, Document, Query
from embedding_service import EmbeddingService
from app import db

logger = logging.getLogger(__name__)

class QueryAnalyzer:
    """Analyzes queries and generates structured responses"""
    
    def __init__(self):
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found in environment variables")
        
        self.client = OpenAI(api_key=self.openai_api_key) if self.openai_api_key else None
        self.embedding_service = EmbeddingService()
        
        # Domain-specific patterns
        self.domain_patterns = {
            "insurance": {
                "keywords": ["coverage", "deductible", "premium", "claim", "policy", "exclusion", "benefit"],
                "entities": ["medical", "dental", "vision", "surgery", "treatment", "medication"]
            },
            "legal": {
                "keywords": ["liability", "breach", "contract", "penalty", "clause", "obligation", "rights"],
                "entities": ["deadline", "termination", "damages", "jurisdiction", "dispute"]
            },
            "hr": {
                "keywords": ["employee", "leave", "benefits", "termination", "policy", "vacation", "sick"],
                "entities": ["maternity", "paternity", "compensation", "performance", "disciplinary"]
            },
            "compliance": {
                "keywords": ["regulation", "requirement", "violation", "fine", "reporting", "audit"],
                "entities": ["deadline", "penalty", "disclosure", "documentation", "certification"]
            }
        }
    
    def analyze_query(self, query_text: str, document_id: int) -> Dict[str, Any]:
        """Main method to analyze query and return structured response"""
        try:
            if not self.client:
                return self._create_error_response("OpenAI API not available")
            
            # Get document
            document = Document.query.get(document_id)
            if not document:
                return self._create_error_response(f"Document {document_id} not found")
            
            # Parse query intent and entities
            parsed_query = self._parse_query(query_text)
            
            # Find relevant chunks using semantic search
            relevant_chunks = self._find_relevant_chunks(query_text, document_id)
            
            if not relevant_chunks:
                return self._create_no_match_response(query_text)
            
            # Analyze chunks and generate structured response
            response = self._generate_structured_response(
                query_text, parsed_query, relevant_chunks, document.filename
            )
            
            # Save query to database
            self._save_query_history(query_text, document_id, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error analyzing query: {str(e)}")
            return self._create_error_response(f"Analysis failed: {str(e)}")
    
    def _parse_query(self, query_text: str) -> Dict[str, Any]:
        """Parse query to extract intent and entities"""
        try:
            # Detect domain
            domain = self._detect_domain(query_text)
            
            # Use OpenAI to parse the query
            if not self.client:
                return {
                    "intent": "general_inquiry",
                    "entity": "unknown",
                    "attributes": [],
                    "domain": "general"
                }
            
            system_prompt = f"""
            You are a query parser for {domain} documents. Extract the intent and entities from the user query.
            
            Return JSON with this structure:
            {{
                "intent": "coverage_check|policy_lookup|condition_check|general_inquiry",
                "entity": "main subject being asked about",
                "attributes": ["list", "of", "specific", "aspects", "requested"],
                "domain": "{domain}"
            }}
            """
            
            response = self.client.chat.completions.create(
                model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024. do not change this unless explicitly requested by the user
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query_text}
                ],
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            if content:
                return json.loads(content)
            else:
                return {
                    "intent": "general_inquiry",
                    "entity": "unknown",
                    "attributes": [],
                    "domain": "general"
                }
            
        except Exception as e:
            logger.error(f"Error parsing query: {str(e)}")
            return {
                "intent": "general_inquiry",
                "entity": "unknown",
                "attributes": [],
                "domain": "general"
            }
    
    def _detect_domain(self, query_text: str) -> str:
        """Detect the domain of the query based on keywords"""
        query_lower = query_text.lower()
        domain_scores = {}
        
        for domain, patterns in self.domain_patterns.items():
            score = 0
            for keyword in patterns["keywords"]:
                if keyword in query_lower:
                    score += 2
            for entity in patterns["entities"]:
                if entity in query_lower:
                    score += 1
            domain_scores[domain] = score
        
        # Return domain with highest score, default to insurance
        if any(domain_scores.values()):
            return max(domain_scores.items(), key=lambda x: x[1])[0]
        else:
            return "insurance"
    
    def _find_relevant_chunks(self, query_text: str, document_id: int, top_k: int = 10) -> List[Dict[str, Any]]:
        """Find relevant document chunks using semantic search or fallback text search"""
        try:
            # Try semantic search first
            similar_chunks = self.embedding_service.search_similar_chunks(query_text, top_k)
            
            if similar_chunks:
                # Filter chunks for this document and get chunk details
                relevant_chunks = []
                chunk_ids = [chunk_id for chunk_id, _ in similar_chunks]
                
                chunks = DocumentChunk.query.filter(
                    DocumentChunk.id.in_(chunk_ids),
                    DocumentChunk.document_id == document_id
                ).all()
                
                # Create chunk dictionary for easy lookup
                chunk_dict = {chunk.id: chunk for chunk in chunks}
                
                # Build relevant chunks with similarity scores
                for chunk_id, similarity_score in similar_chunks:
                    if chunk_id in chunk_dict:
                        chunk = chunk_dict[chunk_id]
                        relevant_chunks.append({
                            "chunk_id": chunk.id,
                            "content": chunk.content,
                            "page_number": chunk.page_number,
                            "similarity_score": similarity_score,
                            "chunk_index": chunk.chunk_index
                        })
                
                # Sort by similarity score
                relevant_chunks.sort(key=lambda x: x["similarity_score"], reverse=True)
                
                logger.debug(f"Found {len(relevant_chunks)} relevant chunks using embeddings")
                return relevant_chunks[:5]  # Return top 5 most relevant
            
            else:
                # Fallback to simple text search
                logger.info("Using fallback text search due to embedding unavailability")
                return self._fallback_text_search(query_text, document_id, top_k)
            
        except Exception as e:
            logger.error(f"Error finding relevant chunks: {str(e)}")
            # Try fallback text search as last resort
            return self._fallback_text_search(query_text, document_id, top_k)
    
    def _fallback_text_search(self, query_text: str, document_id: int, top_k: int = 5) -> List[Dict[str, Any]]:
        """Fallback text-based search when embeddings are unavailable"""
        try:
            # Get all chunks for this document
            chunks = DocumentChunk.query.filter_by(document_id=document_id).all()
            
            if not chunks:
                return []
            
            # Simple keyword matching
            query_words = query_text.lower().split()
            scored_chunks = []
            
            for chunk in chunks:
                content_lower = chunk.content.lower()
                score = 0
                
                # Count keyword matches
                for word in query_words:
                    if len(word) > 2:  # Skip very short words
                        score += content_lower.count(word)
                
                # Add partial matches
                for word in query_words:
                    if len(word) > 3:
                        for content_word in content_lower.split():
                            if word in content_word:
                                score += 0.5
                
                if score > 0:
                    scored_chunks.append({
                        "chunk_id": chunk.id,
                        "content": chunk.content,
                        "page_number": chunk.page_number,
                        "similarity_score": score,
                        "chunk_index": chunk.chunk_index
                    })
            
            # Sort by score (descending)
            scored_chunks.sort(key=lambda x: x["similarity_score"], reverse=True)
            
            logger.debug(f"Found {len(scored_chunks)} relevant chunks using text search")
            return scored_chunks[:top_k]
            
        except Exception as e:
            logger.error(f"Error in fallback text search: {str(e)}")
            return []
    
    def _generate_structured_response(self, query_text: str, parsed_query: Dict[str, Any], 
                                    relevant_chunks: List[Dict[str, Any]], filename: str) -> Dict[str, Any]:
        """Generate structured JSON response using OpenAI"""
        try:
            # Prepare context from relevant chunks
            context_parts = []
            source_references = []
            
            for chunk in relevant_chunks:
                context_parts.append(f"[Page {chunk['page_number']}] {chunk['content']}")
                source_references.append({
                    "document": filename,
                    "page": chunk["page_number"],
                    "chunk_id": chunk["chunk_id"],
                    "similarity_score": round(chunk["similarity_score"], 3)
                })
            
            context = "\n\n".join(context_parts)
            
            # Create system prompt for structured analysis
            system_prompt = f"""
            You are an expert document analyst specializing in {parsed_query.get('domain', 'general')} documents.
            Analyze the provided document context and answer the user's query with a structured JSON response.
            
            IMPORTANT RULES:
            1. Base your answer ONLY on the provided document context
            2. Never hallucinate or make assumptions not supported by the text
            3. Decision must be exactly "Yes", "No", or "Partially"
            4. If "No", conditions array must be empty
            5. Keep explanation under 80 words
            6. Include specific clause references when possible
            
            Return JSON in this exact format:
            {{
                "query": "{query_text}",
                "answer": {{
                    "decision": "Yes|No|Partially",
                    "conditions": ["list of conditions if Yes/Partially, empty if No"]
                }},
                "source_references": [
                    {{
                        "document": "{filename}",
                        "page": page_number,
                        "clause": "specific clause reference if identifiable"
                    }}
                ],
                "explanation": "Clear explanation under 80 words based on document text"
            }}
            """
            
            user_prompt = f"""
            Query: {query_text}
            
            Document Context:
            {context}
            
            Please analyze this context and provide a structured response to the query.
            """
            
            if not self.client:
                return self._create_fallback_response(query_text, relevant_chunks, filename)
            
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024. do not change this unless explicitly requested by the user
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                if content:
                    result = json.loads(content)
                else:
                    return self._create_error_response("No response content from OpenAI")
            except Exception as e:
                error_msg = str(e)
                if "insufficient_quota" in error_msg or "429" in error_msg:
                    logger.warning("OpenAI quota exceeded, using fallback response")
                    return self._create_fallback_response(query_text, relevant_chunks, filename)
                else:
                    return self._create_error_response(f"OpenAI API error: {error_msg}")
            
            # Enhance source references with our detailed info
            if "source_references" in result:
                for i, ref in enumerate(result["source_references"]):
                    if i < len(source_references):
                        ref.update(source_references[i])
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating structured response: {str(e)}")
            return self._create_error_response(f"Failed to generate response: {str(e)}")
    
    def _save_query_history(self, query_text: str, document_id: int, response: Dict[str, Any]):
        """Save query and response to database"""
        try:
            query_record = Query()
            query_record.query_text = query_text
            query_record.document_id = document_id
            query_record.response_json = json.dumps(response)
            db.session.add(query_record)
            db.session.commit()
            logger.debug("Query saved to history")
        except Exception as e:
            logger.error(f"Error saving query history: {str(e)}")
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error response"""
        return {
            "error": True,
            "message": error_message,
            "query": "",
            "answer": {
                "decision": "No",
                "conditions": []
            },
            "source_references": [],
            "explanation": "Error occurred during processing"
        }
    
    def _create_no_match_response(self, query_text: str) -> Dict[str, Any]:
        """Create response when no relevant content is found"""
        return {
            "query": query_text,
            "answer": {
                "decision": "No",
                "conditions": []
            },
            "source_references": [],
            "explanation": "No relevant information found in the document to answer this query."
        }
    
    def get_query_history(self, document_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent query history for a document"""
        try:
            queries = Query.query.filter_by(document_id=document_id)\
                .order_by(Query.created_at.desc())\
                .limit(limit).all()
            
            history = []
            for query in queries:
                try:
                    response_data = json.loads(query.response_json)
                    history.append({
                        "query": query.query_text,
                        "response": response_data,
                        "timestamp": query.created_at.isoformat()
                    })
                except json.JSONDecodeError:
                    continue
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting query history: {str(e)}")
            return []
    
    def _create_fallback_response(self, query_text: str, relevant_chunks: List[Dict[str, Any]], filename: str) -> Dict[str, Any]:
        """Create a basic response when OpenAI is unavailable"""
        try:
            if not relevant_chunks:
                return self._create_no_match_response(query_text)
            
            # Simple analysis without LLM
            decision = "Partially"  # Conservative default
            conditions = []
            explanation = f"Found {len(relevant_chunks)} relevant section(s) in the document."
            
            # Basic keyword-based analysis
            query_lower = query_text.lower()
            combined_content = " ".join([chunk["content"] for chunk in relevant_chunks]).lower()
            
            # Check for common patterns
            if any(word in query_lower for word in ["cover", "include", "eligible", "benefit"]):
                if any(word in combined_content for word in ["yes", "covered", "included", "eligible"]):
                    decision = "Yes"
                elif any(word in combined_content for word in ["no", "not covered", "excluded", "not eligible"]):
                    decision = "No"
            
            # Extract potential conditions from content
            content_sentences = combined_content.split(".")
            for sentence in content_sentences[:3]:  # Check first few sentences
                if any(word in sentence for word in ["require", "must", "need", "condition", "if"]):
                    clean_sentence = sentence.strip().capitalize()
                    if len(clean_sentence) > 10 and len(clean_sentence) < 100:
                        conditions.append(clean_sentence)
            
            # Build source references
            source_references = []
            for chunk in relevant_chunks[:3]:  # Top 3 chunks
                source_references.append({
                    "document": filename,
                    "page": chunk.get("page_number", 1),
                    "similarity_score": chunk.get("similarity_score", 0),
                    "clause": f"Section {chunk.get('chunk_index', 0) + 1}"
                })
            
            return {
                "query": query_text,
                "answer": {
                    "decision": decision,
                    "conditions": conditions[:3] if conditions else []  # Limit to 3 conditions
                },
                "source_references": source_references,
                "explanation": explanation + " (Analysis limited due to API constraints)"
            }
            
        except Exception as e:
            logger.error(f"Error creating fallback response: {str(e)}")
            return self._create_no_match_response(query_text)
