import { useState } from 'react'
import { accountsAPI } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { X, Info } from 'lucide-react'
import './AddAccountModal.css'

export default function AddAccountModal({ onClose }) {
  const [name, setName] = useState('')
  const [accessKeyId, setAccessKeyId] = useState('')
  const [secretAccessKey, setSecretAccessKey] = useState('')
  const [region, setRegion] = useState('us-east-1')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  const { loadAccounts, switchAccount } = useAuth()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    
    try {
      const res = await accountsAPI.create({
        name,
        access_key_id: accessKeyId,
        secret_access_key: secretAccessKey,
        region
      })
      await loadAccounts()
      switchAccount(res.data.id)
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add account')
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-header">
          <h2>Add AWS Account</h2>
          <button className="icon-btn" onClick={onClose}><X size={20} /></button>
        </div>
        
        <div className="modal-body">
          <div className="info-box">
            <Info size={20} color="var(--accent-primary)" style={{ flexShrink: 0 }} />
            <p>
              Please provide credentials for an IAM User with <strong>ReadOnlyAccess</strong>.
              Your secret key will be encrypted before being saved.
            </p>
          </div>

          {error && <div className="modal-error">{error}</div>}

          <form onSubmit={handleSubmit} className="account-form">
            <div className="form-group">
              <label>Account Name / Alias</label>
              <input 
                type="text" 
                value={name} 
                onChange={e => setName(e.target.value)} 
                placeholder="e.g. Production Account"
                required 
              />
            </div>
            
            <div className="form-group">
              <label>Default Region</label>
              <input 
                type="text" 
                value={region} 
                onChange={e => setRegion(e.target.value)} 
                placeholder="e.g. us-east-1"
                required 
              />
            </div>
            
            <div className="form-group">
              <label>Access Key ID</label>
              <input 
                type="text" 
                value={accessKeyId} 
                onChange={e => setAccessKeyId(e.target.value)} 
                required 
              />
            </div>
            
            <div className="form-group">
              <label>Secret Access Key</label>
              <input 
                type="password" 
                value={secretAccessKey} 
                onChange={e => setSecretAccessKey(e.target.value)} 
                required 
              />
            </div>
            
            <div className="modal-actions">
              <button type="button" className="btn-secondary" onClick={onClose} disabled={loading}>
                Cancel
              </button>
              <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? 'Verifying...' : 'Add Account'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
