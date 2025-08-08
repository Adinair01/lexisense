import os
import logging
from flask import Blueprint, request, jsonify
from functools import wraps
from document_processor import DocumentProcessor
from embedding_service import EmbeddingService
from query_analyzer import QueryAnalyzer
from models import Document, DocumentChunk

logger = logging.getLogger(__name__)

# Create API blueprint
api_bp = Blueprint('api', __name__)

# Bearer token for authentication
BEARER_TOKEN = "fa68b140b45219c548b69d0e993fc8a7b738eb467a75eb70c1390fa21b5ec940"

def require_auth(f):
    """Decorator to require bearer token authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authorization header required"}), 401
        
        token = auth_header.split(' ')[1]
        if token != BEARER_TOKEN:
            return jsonify({"error": "Invalid token"}), 401
        
        return f(*args, **kwargs)
    return decorated_function

@api_bp.route('/', methods=['POST'])
@require_auth
def process_query():
    """Main API endpoint for processing queries"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        # Extract required fields
        query_text = data.get('query')
        document_url = data.get('document_url')
        document_id = data.get('document_id')
        
        if not query_text:
            return jsonify({"error": "Query text is required"}), 400
        
        # Process document if URL provided
        if document_url and not document_id:
            processor = DocumentProcessor()
            try:
                document = processor.process_pdf_from_url(document_url)
                if not document:
                    return jsonify({"error": "Failed to process document from URL - no content extracted"}), 400
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                return jsonify({"error": f"URL processing failed: {str(e)}"}), 400
            
            # Add embeddings for the new document
            embedding_service = EmbeddingService()
            chunks = [(chunk.id, chunk.content) for chunk in document.chunks] if document.chunks else []
            
            if not embedding_service.add_chunk_embeddings(chunks):
                logger.warning(f"Failed to add embeddings for document {document.id} - document uploaded but search may be limited")
            
            document_id = document.id
        
        if not document_id:
            return jsonify({"error": "Document ID or document URL is required"}), 400
        
        # Analyze query
        analyzer = QueryAnalyzer()
        response = analyzer.analyze_query(query_text, document_id)
        
        if response.get('error'):
            return jsonify(response), 400
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@api_bp.route('/upload', methods=['POST'])
@require_auth
def upload_document():
    """Upload and process a PDF document"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Only PDF files are supported"}), 400
        
        # Process the uploaded file
        processor = DocumentProcessor()
        file_data = file.read()
        filename = file.filename or 'uploaded_document.pdf'
        
        try:
            document = processor.process_pdf_upload(file_data, filename)
            if not document:
                return jsonify({"error": "Failed to process PDF file - no content extracted"}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Upload failed: {str(e)}"}), 400
        
        # Add embeddings for the document
        embedding_service = EmbeddingService()
        chunks = [(chunk.id, chunk.content) for chunk in document.chunks] if document.chunks else []
        
        if not embedding_service.add_chunk_embeddings(chunks):
            logger.warning(f"Failed to add embeddings for document {document.id} - document uploaded but search may be limited")
        
        return jsonify({
            "document_id": document.id,
            "filename": document.filename,
            "chunks_count": document.chunks_count,
            "message": "Document processed successfully"
        })
        
    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500

@api_bp.route('/documents', methods=['GET'])
@require_auth
def list_documents():
    """List all processed documents"""
    try:
        documents = Document.query.order_by(Document.created_at.desc()).all()
        
        result = []
        for doc in documents:
            result.append({
                "id": doc.id,
                "filename": doc.filename,
                "url": doc.url,
                "chunks_count": doc.chunks_count,
                "created_at": doc.created_at.isoformat()
            })
        
        return jsonify({"documents": result})
        
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        return jsonify({"error": f"Failed to list documents: {str(e)}"}), 500

@api_bp.route('/documents/<int:document_id>', methods=['GET'])
@require_auth
def get_document(document_id):
    """Get document details and recent queries"""
    try:
        document = Document.query.get_or_404(document_id)
        
        # Get recent queries
        analyzer = QueryAnalyzer()
        recent_queries = analyzer.get_query_history(document_id, limit=5)
        
        return jsonify({
            "id": document.id,
            "filename": document.filename,
            "url": document.url,
            "chunks_count": document.chunks_count,
            "created_at": document.created_at.isoformat(),
            "recent_queries": recent_queries
        })
        
    except Exception as e:
        logger.error(f"Error getting document {document_id}: {str(e)}")
        return jsonify({"error": f"Failed to get document: {str(e)}"}), 500

@api_bp.route('/documents/<int:document_id>', methods=['DELETE'])
@require_auth
def delete_document(document_id):
    """Delete a document and its embeddings"""
    try:
        document = Document.query.get_or_404(document_id)
        
        # Remove embeddings from index
        embedding_service = EmbeddingService()
        embedding_service.remove_document_embeddings(document_id)
        
        # Delete from database
        DocumentChunk.query.filter_by(document_id=document_id).delete()
        Document.query.filter_by(id=document_id).delete()
        
        from app import db
        db.session.commit()
        
        return jsonify({"message": "Document deleted successfully"})
        
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {str(e)}")
        return jsonify({"error": f"Failed to delete document: {str(e)}"}), 500

@api_bp.route('/stats', methods=['GET'])
@require_auth
def get_stats():
    """Get system statistics"""
    try:
        embedding_service = EmbeddingService()
        stats = embedding_service.get_index_stats()
        
        # Add database stats
        total_documents = Document.query.count()
        total_chunks = DocumentChunk.query.count()
        
        # Check Gemini API status
        gemini_status = "available"
        try:
            # Test Gemini API availability
            from query_analyzer import QueryAnalyzer
            analyzer = QueryAnalyzer()
            if analyzer.client:
                gemini_status = "available"
            else:
                gemini_status = "error"
        except Exception as e:
            if "quota" in str(e).lower() or "429" in str(e):
                gemini_status = "quota_exceeded"
            else:
                gemini_status = "error"
        
        stats.update({
            "total_documents": total_documents,
            "total_chunks_db": total_chunks,
            "gemini_status": gemini_status,
            "openai_status": "quota_exceeded"  # Keep for frontend compatibility
        })
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({"error": f"Failed to get stats: {str(e)}"}), 500
