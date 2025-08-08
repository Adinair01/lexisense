import os
import hashlib
import logging
import requests
from typing import List, Tuple, Optional
import io

import pdfplumber
import PyPDF2

from models import Document, DocumentChunk
from app import db

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Handles PDF document processing and text extraction"""
    
    def __init__(self):
        self.max_chunk_size = 1500
        self.min_chunk_size = 500
        self.overlap_size = 200
    
    def process_pdf_from_url(self, pdf_url: str) -> Optional[Document]:
        """Download and process PDF from URL"""
        try:
            logger.info(f"Downloading PDF from URL: {pdf_url}")
            response = requests.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            pdf_content = response.content
            filename = pdf_url.split('/')[-1] or 'document.pdf'
            
            return self._process_pdf_content(pdf_content, filename, pdf_url)
            
        except Exception as e:
            logger.error(f"Error downloading PDF from URL {pdf_url}: {str(e)}")
            return None
    
    def process_pdf_upload(self, file_data: bytes, filename: str) -> Optional[Document]:
        """Process uploaded PDF file"""
        try:
            return self._process_pdf_content(file_data, filename)
        except Exception as e:
            logger.error(f"Error processing uploaded PDF {filename}: {str(e)}")
            return None
    
    def _process_pdf_content(self, pdf_content: bytes, filename: str, url: Optional[str] = None) -> Optional[Document]:
        """Process PDF content and extract text"""
        try:
            # Generate file hash to avoid duplicates
            file_hash = hashlib.sha256(pdf_content).hexdigest()
            
            # Check if document already exists
            existing_doc = Document.query.filter_by(file_hash=file_hash).first()
            if existing_doc:
                logger.info(f"Document already exists: {filename}")
                return existing_doc
            
            # Extract text from PDF
            text_content, page_info = self._extract_text_from_pdf(pdf_content)
            
            if not text_content.strip():
                logger.warning(f"No text content extracted from PDF: {filename}")
                return None
            
            # Create document record
            document = Document()
            document.filename = filename
            document.url = url
            document.content = text_content
            document.file_hash = file_hash
            
            db.session.add(document)
            db.session.flush()  # Get the document ID
            
            # Create chunks
            chunks = self._create_chunks(text_content, page_info)
            chunk_records = []
            
            for i, (chunk_text, page_num, start_char, end_char) in enumerate(chunks):
                chunk_record = DocumentChunk()
                chunk_record.document_id = document.id
                chunk_record.chunk_index = i
                chunk_record.content = chunk_text
                chunk_record.page_number = page_num
                chunk_record.start_char = start_char
                chunk_record.end_char = end_char
                chunk_records.append(chunk_record)
            
            db.session.add_all(chunk_records)
            document.chunks_count = len(chunk_records)
            
            db.session.commit()
            logger.info(f"Successfully processed document: {filename} with {len(chunk_records)} chunks")
            
            return document
            
        except ValueError as e:
            db.session.rollback()
            logger.error(f"PDF validation error: {str(e)}")
            raise e
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing PDF content: {str(e)}")
            raise Exception(f"Document processing failed: {str(e)}")
    
    def _extract_text_from_pdf(self, pdf_content: bytes) -> Tuple[str, List[Tuple[int, int, int]]]:
        """Extract text from PDF and return with page information"""
        text_content = ""
        page_info = []  # (page_num, start_char, end_char)
        
        try:
            # Try pdfplumber first (preferred)
            try:
                with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                    for page_num, page in enumerate(pdf.pages, 1):
                        start_char = len(text_content)
                        page_text = page.extract_text() or ""
                        text_content += page_text + "\n"
                        end_char = len(text_content)
                        page_info.append((page_num, start_char, end_char))
            except Exception:
                # Fallback to PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    start_char = len(text_content)
                    page_text = page.extract_text() or ""
                    text_content += page_text + "\n"
                    end_char = len(text_content)
                    page_info.append((page_num, start_char, end_char))
                    
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            if "EOF marker not found" in str(e) or "Invalid PDF" in str(e):
                raise ValueError("Invalid PDF file format. Please upload a valid PDF document.")
            else:
                raise ValueError(f"PDF processing failed: {str(e)}")
        
        return text_content, page_info
    
    def _create_chunks(self, text: str, page_info: List[Tuple[int, int, int]]) -> List[Tuple[str, int, int, int]]:
        """Create overlapping chunks from text with page tracking"""
        chunks = []
        words = text.split()
        
        if not words:
            return chunks
        
        current_chunk = []
        current_chunk_size = 0
        chunk_start_char = 0
        
        for i, word in enumerate(words):
            word_size = len(word) + 1  # +1 for space
            
            # If adding this word would exceed max_chunk_size, finalize current chunk
            if current_chunk_size + word_size > self.max_chunk_size and len(current_chunk) > 0:
                chunk_text = ' '.join(current_chunk)
                chunk_end_char = chunk_start_char + len(chunk_text)
                
                # Find which page this chunk belongs to
                page_num = self._find_page_for_position(chunk_start_char, page_info)
                
                chunks.append((chunk_text, page_num, chunk_start_char, chunk_end_char))
                
                # Start new chunk with overlap
                overlap_words = current_chunk[-self._calculate_overlap_words(current_chunk):]
                current_chunk = overlap_words + [word]
                chunk_start_char = chunk_end_char - len(' '.join(overlap_words))
                current_chunk_size = len(' '.join(current_chunk))
            else:
                current_chunk.append(word)
                current_chunk_size += word_size
        
        # Add final chunk if it exists and meets minimum size
        if current_chunk and current_chunk_size >= self.min_chunk_size:
            chunk_text = ' '.join(current_chunk)
            chunk_end_char = chunk_start_char + len(chunk_text)
            page_num = self._find_page_for_position(chunk_start_char, page_info)
            chunks.append((chunk_text, page_num, chunk_start_char, chunk_end_char))
        
        return chunks
    
    def _calculate_overlap_words(self, chunk: List[str]) -> int:
        """Calculate number of overlap words based on overlap_size"""
        overlap_chars = 0
        overlap_words = 0
        
        for word in reversed(chunk):
            if overlap_chars + len(word) + 1 <= self.overlap_size:
                overlap_chars += len(word) + 1
                overlap_words += 1
            else:
                break
        
        return overlap_words
    
    def _find_page_for_position(self, char_position: int, page_info: List[Tuple[int, int, int]]) -> int:
        """Find which page a character position belongs to"""
        for page_num, start_char, end_char in page_info:
            if start_char <= char_position < end_char:
                return page_num
        
        # If not found, return the last page
        return page_info[-1][0] if page_info else 1
