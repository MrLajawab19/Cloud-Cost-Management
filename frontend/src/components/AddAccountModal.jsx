import { useState } from 'react'
import { accountsAPI } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { X, Info } from 'lucide-react'
import './AddAccountModal.css'

export default function AddAccountModal({ onClose }) {
  const [provider, setProvider] = useState('aws')
  
  const [name, setName] = useState('')
  const [region, setRegion] = useState('us-east-1')
  
  // AWS State
  const [accessKeyId, setAccessKeyId] = useState('')
  const [secretAccessKey, setSecretAccessKey] = useState('')
  
  // Azure State
  const [tenantId, setTenantId] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [subscriptionId, setSubscriptionId] = useState('')
  
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  const { loadAccounts, switchAccount } = useAuth()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    
    try {
      const payload = {
        name,
        provider,
        region,
      }
      
      if (provider === 'aws') {
        payload.access_key_id = accessKeyId
        payload.secret_access_key = secretAccessKey
      } else {
        payload.tenant_id = tenantId
        payload.client_id = clientId
        payload.client_secret = clientSecret
        payload.subscription_id = subscriptionId
      }
      
      const res = await accountsAPI.create(payload)
      await loadAccounts()
      switchAccount(res.data.id)
      onClose()
    } catch (err) {
      const detail = err.response?.data?.detail
      if (Array.isArray(detail)) {
        setError(detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', '))
      } else if (typeof detail === 'string') {
        setError(detail)
      } else {
        setError('Failed to add account')
      }
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-header">
          <h2>Add Cloud Account</h2>
          <button className="icon-btn" onClick={onClose}><X size={20} /></button>
        </div>
        
        <div className="modal-body">
          <div className="provider-tabs">
            <button 
              type="button"
              className={`tab-btn ${provider === 'aws' ? 'active' : ''}`}
              onClick={() => {
                setProvider('aws')
                setRegion('us-east-1')
              }}
            >
              AWS
            </button>
            <button 
              type="button"
              className={`tab-btn ${provider === 'azure' ? 'active' : ''}`}
              onClick={() => {
                setProvider('azure')
                setRegion('eastus')
              }}
            >
              Azure
            </button>
          </div>
          
          <div className="info-box">
            <Info size={20} color="var(--accent-primary)" style={{ flexShrink: 0 }} />
            <p>
              {provider === 'aws' 
                ? "Please provide credentials for an IAM User with ReadOnlyAccess. Your secret key will be encrypted."
                : "Please provide a Service Principal with Reader access. Your client secret will be encrypted."}
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
                placeholder={provider === 'aws' ? "e.g. us-east-1" : "e.g. eastus"}
                required 
              />
            </div>
            
            {provider === 'aws' ? (
              <>
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
              </>
            ) : (
              <>
                <div className="form-group">
                  <label>Tenant ID</label>
                  <input 
                    type="text" 
                    value={tenantId} 
                    onChange={e => setTenantId(e.target.value)} 
                    required 
                  />
                </div>
                <div className="form-group">
                  <label>Client ID (App ID)</label>
                  <input 
                    type="text" 
                    value={clientId} 
                    onChange={e => setClientId(e.target.value)} 
                    required 
                  />
                </div>
                <div className="form-group">
                  <label>Client Secret</label>
                  <input 
                    type="password" 
                    value={clientSecret} 
                    onChange={e => setClientSecret(e.target.value)} 
                    required 
                  />
                </div>
                <div className="form-group">
                  <label>Subscription ID</label>
                  <input 
                    type="text" 
                    value={subscriptionId} 
                    onChange={e => setSubscriptionId(e.target.value)} 
                    required 
                  />
                </div>
              </>
            )}
            
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
