// Document Analysis System Frontend JavaScript

class DocumentAnalysisApp {
    constructor() {
        this.bearerToken = 'fa68b140b45219c548b69d0e993fc8a7b738eb467a75eb70c1390fa21b5ec940';
        this.selectedDocumentId = null;
        this.documents = [];
        
        this.initializeEventListeners();
        this.loadDocuments();
        this.checkSystemStatus();
    }

    initializeEventListeners() {
        // Upload button
        document.getElementById('uploadBtn').addEventListener('click', () => this.handleUpload());
        
        // Query button
        document.getElementById('queryBtn').addEventListener('click', () => this.handleQuery());
        
        // Stats button
        document.getElementById('statsBtn').addEventListener('click', () => this.showStats());
        
        // Enter key in query input
        document.getElementById('queryInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                this.handleQuery();
            }
        });
        
        // File input change
        document.getElementById('fileUpload').addEventListener('change', () => {
            const fileInput = document.getElementById('fileUpload');
            const urlInput = document.getElementById('documentUrl');
            if (fileInput.files.length > 0) {
                urlInput.value = ''; // Clear URL if file is selected
            }
        });
        
        // URL input change
        document.getElementById('documentUrl').addEventListener('input', () => {
            const fileInput = document.getElementById('fileUpload');
            const urlInput = document.getElementById('documentUrl');
            if (urlInput.value.trim()) {
                fileInput.value = ''; // Clear file if URL is entered
            }
        });
    }

    async makeApiRequest(url, options = {}) {
        try {
            const defaultOptions = {
                headers: {
                    'Authorization': `Bearer ${this.bearerToken}`,
                    'Content-Type': 'application/json'
                }
            };

            console.log('Making API request to:', url);
            
            const response = await fetch(url, {
                ...defaultOptions,
                ...options,
                headers: {
                    ...defaultOptions.headers,
                    ...options.headers
                }
            });

            console.log('Response status:', response.status);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                console.error('API error response:', errorData);
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            console.log('API response:', result);
            return result;
        } catch (error) {
            console.error('API request failed:', error);
            console.error('Error details:', {
                message: error.message,
                stack: error.stack,
                url: url,
                options: options
            });
            throw error;
        }
    }

    async loadDocuments() {
        try {
            const data = await this.makeApiRequest('/api/v1/documents');
            this.documents = data.documents;
            this.updateDocumentsList();
            this.updateDocumentSelect();
        } catch (error) {
            this.showToast('Failed to load documents', 'error');
            console.error('Error loading documents:', error);
        }
    }

    async checkSystemStatus() {
        try {
            const stats = await this.makeApiRequest('/api/v1/stats');
            this.updateStatusIndicator(stats.openai_status);
        } catch (error) {
            this.updateStatusIndicator('error');
            console.error('Error checking system status:', error);
        }
    }

    updateStatusIndicator(status) {
        const indicator = document.getElementById('statusIndicator');
        const badge = document.getElementById('statusBadge');
        const text = document.getElementById('statusText');
        
        indicator.style.display = 'block';
        
        switch(status) {
            case 'available':
                badge.className = 'badge bg-success';
                text.textContent = 'API Ready';
                break;
            case 'quota_exceeded':
                badge.className = 'badge bg-warning text-dark';
                text.textContent = 'Quota Exceeded';
                break;
            case 'error':
            default:
                badge.className = 'badge bg-danger';
                text.textContent = 'API Error';
                break;
        }
    }

    updateDocumentsList() {
        const container = document.getElementById('documentsList');
        
        if (this.documents.length === 0) {
            container.innerHTML = `
                <div class="list-group-item text-center text-muted py-4">
                    <i class="fas fa-file-alt fa-2x mb-2"></i>
                    <p class="mb-0">No documents uploaded yet</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.documents.map(doc => `
            <div class="list-group-item document-item ${doc.id === this.selectedDocumentId ? 'active' : ''}" 
                 data-document-id="${doc.id}">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1" onclick="app.selectDocument(${doc.id})">
                        <h6 class="mb-1">${this.escapeHtml(doc.filename)}</h6>
                        <small class="text-muted">
                            ${doc.chunks_count} chunks • 
                            ${new Date(doc.created_at).toLocaleDateString()}
                        </small>
                    </div>
                    <button class="btn btn-sm btn-outline-danger ms-2" 
                            onclick="app.deleteDocument(${doc.id})" 
                            title="Delete document">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    }

    updateDocumentSelect() {
        const select = document.getElementById('selectedDocument');
        select.innerHTML = '<option value="">Select a document...</option>';
        
        this.documents.forEach(doc => {
            const option = document.createElement('option');
            option.value = doc.id;
            option.textContent = doc.filename;
            if (doc.id === this.selectedDocumentId) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    }

    selectDocument(documentId) {
        this.selectedDocumentId = documentId;
        document.getElementById('selectedDocument').value = documentId;
        this.updateDocumentsList();
    }

    async handleUpload() {
        const fileInput = document.getElementById('fileUpload');
        const urlInput = document.getElementById('documentUrl');
        const uploadBtn = document.getElementById('uploadBtn');
        
        const file = fileInput.files[0];
        const url = urlInput.value.trim();
        
        if (!file && !url) {
            this.showToast('Please select a file or enter a URL', 'warning');
            return;
        }

        if (file && !file.type.includes('pdf')) {
            this.showToast('Please select a PDF file', 'warning');
            return;
        }

        try {
            uploadBtn.disabled = true;
            uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';

            let response;

            if (file) {
                // Upload file
                const formData = new FormData();
                formData.append('file', file);
                
                response = await this.makeApiRequest('/api/v1/upload', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'Authorization': `Bearer ${this.bearerToken}`
                        // Don't set Content-Type for FormData, let browser set it
                    }
                });
            } else {
                // Process URL
                response = await this.makeApiRequest('/api/v1/', {
                    method: 'POST',
                    body: JSON.stringify({
                        query: 'Document uploaded for processing',
                        document_url: url
                    })
                });
            }

            this.showToast('Document processed successfully!', 'success');
            
            // Clear inputs
            fileInput.value = '';
            urlInput.value = '';
            
            // Reload documents and select the new one
            await this.loadDocuments();
            if (response.document_id) {
                this.selectDocument(response.document_id);
            }

        } catch (error) {
            let errorMessage = error.message;
            if (errorMessage.includes('Invalid PDF file format')) {
                errorMessage = 'Please upload a valid PDF file. The selected file is not a proper PDF document.';
            } else if (errorMessage.includes('quota')) {
                errorMessage = 'OpenAI API quota exceeded. Please try again later or check your API billing.';
            }
            this.showToast(`Upload failed: ${errorMessage}`, 'error');
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> Process Document';
        }
    }

    async handleQuery() {
        const queryInput = document.getElementById('queryInput');
        const queryBtn = document.getElementById('queryBtn');
        const selectedDoc = document.getElementById('selectedDocument').value;
        
        const query = queryInput.value.trim();
        
        if (!query) {
            this.showToast('Please enter a query', 'warning');
            return;
        }

        if (!selectedDoc) {
            this.showToast('Please select a document', 'warning');
            return;
        }

        try {
            queryBtn.disabled = true;
            queryBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';
            
            this.showLoading(true);

            const response = await this.makeApiRequest('/api/v1/', {
                method: 'POST',
                body: JSON.stringify({
                    query: query,
                    document_id: parseInt(selectedDoc)
                })
            });

            this.displayResults(response);
            this.showToast('Query analyzed successfully!', 'success');

        } catch (error) {
            let errorMessage = error.message;
            if (errorMessage.includes('quota')) {
                errorMessage = 'OpenAI API quota exceeded. Document analysis is temporarily unavailable.';
            }
            this.showToast(`Query failed: ${errorMessage}`, 'error');
            this.hideResults();
        } finally {
            queryBtn.disabled = false;
            queryBtn.innerHTML = '<i class="fas fa-search"></i> Analyze Query';
            this.showLoading(false);
        }
    }

    displayResults(response) {
        const resultsCard = document.getElementById('resultsCard');
        const resultsContent = document.getElementById('resultsContent');
        
        const decision = response.answer?.decision || 'Unknown';
        const conditions = response.answer?.conditions || [];
        const sourceRefs = response.source_references || [];
        const explanation = response.explanation || 'No explanation provided';
        
        let decisionClass = 'decision-no';
        if (decision === 'Yes') decisionClass = 'decision-yes';
        else if (decision === 'Partially') decisionClass = 'decision-partially';

        resultsContent.innerHTML = `
            <div class="fade-in-up">
                <div class="mb-4">
                    <h6 class="text-muted mb-2">Query</h6>
                    <p class="bg-secondary-subtle p-3 rounded">${this.escapeHtml(response.query)}</p>
                </div>

                <div class="row mb-4">
                    <div class="col-md-4">
                        <h6 class="text-muted mb-2">Decision</h6>
                        <span class="badge ${decisionClass} decision-badge">${decision}</span>
                    </div>
                    <div class="col-md-8">
                        <h6 class="text-muted mb-2">Explanation</h6>
                        <p class="mb-0">${this.escapeHtml(explanation)}</p>
                    </div>
                </div>

                ${conditions.length > 0 ? `
                    <div class="mb-4">
                        <h6 class="text-muted mb-2">Conditions</h6>
                        <div class="conditions-list">
                            <ul class="mb-0">
                                ${conditions.map(condition => `
                                    <li>${this.escapeHtml(condition)}</li>
                                `).join('')}
                            </ul>
                        </div>
                    </div>
                ` : ''}

                ${sourceRefs.length > 0 ? `
                    <div class="mb-4">
                        <h6 class="text-muted mb-2">Source References</h6>
                        ${sourceRefs.map(ref => `
                            <div class="source-reference">
                                <div class="d-flex justify-content-between align-items-start">
                                    <div>
                                        <strong>${this.escapeHtml(ref.document)}</strong>
                                        ${ref.page ? ` - Page ${ref.page}` : ''}
                                        ${ref.clause ? `<br><small class="text-muted">${this.escapeHtml(ref.clause)}</small>` : ''}
                                    </div>
                                    ${ref.similarity_score ? `
                                        <span class="badge bg-info">
                                            ${(ref.similarity_score * 100).toFixed(1)}% match
                                        </span>
                                    ` : ''}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `;

        resultsCard.style.display = 'block';
        resultsCard.scrollIntoView({ behavior: 'smooth' });
    }

    hideResults() {
        document.getElementById('resultsCard').style.display = 'none';
    }

    async deleteDocument(documentId) {
        if (!confirm('Are you sure you want to delete this document?')) {
            return;
        }

        try {
            await this.makeApiRequest(`/api/v1/documents/${documentId}`, {
                method: 'DELETE'
            });

            this.showToast('Document deleted successfully', 'success');
            
            // Clear selection if deleted document was selected
            if (this.selectedDocumentId === documentId) {
                this.selectedDocumentId = null;
                this.hideResults();
            }
            
            await this.loadDocuments();

        } catch (error) {
            this.showToast(`Failed to delete document: ${error.message}`, 'error');
        }
    }

    async showStats() {
        try {
            const stats = await this.makeApiRequest('/api/v1/stats');
            
            const openaiStatusClass = stats.openai_status === 'available' ? 'text-success' : 
                                      stats.openai_status === 'quota_exceeded' ? 'text-warning' : 'text-danger';
            const openaiStatusText = stats.openai_status === 'available' ? 'Available' : 
                                    stats.openai_status === 'quota_exceeded' ? 'Quota Exceeded' : 'Error';
            
            const statsContent = document.getElementById('statsContent');
            statsContent.innerHTML = `
                <div class="row">
                    <div class="col-6">
                        <div class="stat-item">
                            <div class="stat-number">${stats.total_documents}</div>
                            <div class="stat-label">Documents</div>
                        </div>
                    </div>
                    <div class="col-6">
                        <div class="stat-item">
                            <div class="stat-number">${stats.total_chunks_db}</div>
                            <div class="stat-label">Chunks</div>
                        </div>
                    </div>
                    <div class="col-6">
                        <div class="stat-item">
                            <div class="stat-number">${stats.total_vectors}</div>
                            <div class="stat-label">Embeddings</div>
                        </div>
                    </div>
                    <div class="col-6">
                        <div class="stat-item">
                            <div class="stat-number">${stats.dimension}</div>
                            <div class="stat-label">Dimensions</div>
                        </div>
                    </div>
                </div>
                
                <div class="mt-3">
                    <h6>OpenAI API Status</h6>
                    <span class="badge ${openaiStatusClass}">${openaiStatusText}</span>
                    ${stats.openai_status === 'quota_exceeded' ? 
                        '<p class="text-warning mt-2"><small>⚠️ API quota exceeded. Document analysis features may be limited until quota resets.</small></p>' : 
                        ''
                    }
                </div>
                
                <div class="mt-3">
                    <h6>Bearer Token</h6>
                    <code class="bearer-token">${this.bearerToken}</code>
                </div>
            `;

            const modal = new bootstrap.Modal(document.getElementById('statsModal'));
            modal.show();

        } catch (error) {
            this.showToast(`Failed to load stats: ${error.message}`, 'error');
        }
    }

    showLoading(show) {
        const indicator = document.getElementById('loadingIndicator');
        indicator.style.display = show ? 'block' : 'none';
    }

    showToast(message, type = 'info') {
        const toastContainer = document.getElementById('toastContainer');
        const toastId = 'toast-' + Date.now();
        
        let bgClass = 'bg-info';
        let icon = 'fa-info-circle';
        
        if (type === 'success') {
            bgClass = 'bg-success';
            icon = 'fa-check-circle';
        } else if (type === 'error') {
            bgClass = 'bg-danger';
            icon = 'fa-exclamation-circle';
        } else if (type === 'warning') {
            bgClass = 'bg-warning';
            icon = 'fa-exclamation-triangle';
        }

        const toastElement = document.createElement('div');
        toastElement.className = `toast ${bgClass} text-white`;
        toastElement.id = toastId;
        toastElement.setAttribute('role', 'alert');
        toastElement.innerHTML = `
            <div class="toast-body">
                <i class="fas ${icon} me-2"></i>
                ${this.escapeHtml(message)}
            </div>
        `;

        toastContainer.appendChild(toastElement);

        const toast = new bootstrap.Toast(toastElement, {
            autohide: true,
            delay: type === 'error' ? 5000 : 3000
        });

        toast.show();

        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the application
const app = new DocumentAnalysisApp();

// Handle document select change
document.getElementById('selectedDocument').addEventListener('change', (e) => {
    app.selectedDocumentId = e.target.value ? parseInt(e.target.value) : null;
    app.updateDocumentsList();
});
