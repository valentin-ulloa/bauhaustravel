# 🚀 Deployment Guide - Bauhaus Travel

## 📋 **Pre-Deployment Checklist**

✅ **Database Migrations Applied:**
- [ ] `001_create_notifications_log.sql`
- [ ] `002_create_itineraries.sql` 
- [ ] `003_create_agency_places.sql`
- [ ] `004_create_conversations.sql`
- [ ] `005_create_documents.sql`

✅ **Environment Variables Ready:**
- [ ] SUPABASE_URL
- [ ] SUPABASE_SERVICE_ROLE_KEY
- [ ] TWILIO_ACCOUNT_SID
- [ ] TWILIO_AUTH_TOKEN
- [ ] TWILIO_PHONE_NUMBER
- [ ] OPENAI_API_KEY

---

## 🌐 **Railway Deployment** (Recommended)

### **Step 1: Create Railway Account**
1. Go to [railway.app](https://railway.app/)
2. Sign up with GitHub
3. Connect your repository

### **Step 2: Deploy from GitHub**
```bash
# 1. Push code to GitHub (if not already)
git add .
git commit -m "feat: production deployment ready"
git push origin main

# 2. Railway will auto-detect Python and FastAPI
# 3. It will use our Procfile and railway.toml
```

### **Step 3: Configure Environment Variables**
In Railway dashboard:
1. Go to your app → **Variables**
2. Add each variable from `deployment/env.production.template`:

```bash
ENVIRONMENT=production
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=whatsapp:+13613094264
OPENAI_API_KEY=your-openai-key
PORT=8000
LOG_LEVEL=info
```

### **Step 4: Deploy & Test**
1. Railway auto-deploys on push
2. Get your app URL: `https://your-app.railway.app`
3. Test health check: `GET /health`
4. Test API: `GET /`

---

## 🔧 **Alternative: Heroku Deployment**

### **Option A: Heroku CLI**
```bash
# Install Heroku CLI
brew install heroku/brew/heroku

# Login and create app
heroku login
heroku create bauhaus-travel-api

# Set environment variables
heroku config:set ENVIRONMENT=production
heroku config:set SUPABASE_URL=your-url
heroku config:set SUPABASE_SERVICE_ROLE_KEY=your-key
heroku config:set TWILIO_ACCOUNT_SID=your-sid
heroku config:set TWILIO_AUTH_TOKEN=your-token
heroku config:set TWILIO_PHONE_NUMBER=whatsapp:+13613094264
heroku config:set OPENAI_API_KEY=your-openai-key

# Deploy
git push heroku main
```

### **Option B: GitHub Integration**
1. Connect Heroku to GitHub repository
2. Enable auto-deploys from `main` branch
3. Add environment variables in Heroku dashboard

---

## 🌍 **Alternative: Vercel Deployment**

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Set environment variables in Vercel dashboard
# Domain: https://your-app.vercel.app
```

---

## ✅ **Post-Deployment Testing**

### **1. Health Check**
```bash
curl https://your-app.railway.app/health
# Expected: {"status": "healthy", "timestamp": "..."}
```

### **2. API Endpoints**
```bash
# Test root endpoint
curl https://your-app.railway.app/
# Expected: {"message": "Bauhaus Travel API", "version": "1.0.0"}

# Test trip creation
curl -X POST https://your-app.railway.app/trips \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Test User",
    "whatsapp": "+1234567890",
    "destination": "Miami",
    "departure_date": "2025-06-15",
    "return_date": "2025-06-20",
    "client_description": "Business trip"
  }'
```

### **3. WhatsApp Integration**
1. **Update Twilio Webhook URL:**
   - Go to Twilio Console → WhatsApp Sandbox
   - Set webhook URL: `https://your-app.railway.app/webhooks/twilio`
   
2. **Test Inbound Messages:**
   - Send "Hey" to your WhatsApp number
   - Should get intelligent response from ConciergeAgent

### **4. Test Document API**
```bash
curl -X POST https://your-app.railway.app/documents \
  -H "Content-Type: application/json" \
  -d '{
    "trip_id": "your-trip-uuid",
    "document_type": "boarding_pass",
    "file_url": "https://example.com/boarding_pass.pdf",
    "file_name": "boarding_pass.pdf",
    "uploaded_by": "test@example.com",
    "uploaded_by_type": "user"
  }'
```

---

## 🔒 **Security Checklist**

- [ ] **Environment variables** set (not in code)
- [ ] **HTTPS only** (automatic with Railway/Heroku)
- [ ] **Supabase RLS** enabled on tables
- [ ] **Twilio webhook** authentication (optional)
- [ ] **Rate limiting** (future improvement)

---

## 📊 **Monitoring Setup**

### **Logs**
```bash
# Railway logs
railway logs

# Heroku logs  
heroku logs --tail

# Vercel logs
vercel logs
```

### **Health Monitoring**
- Set up uptime monitoring: [uptimerobot.com](https://uptimerobot.com)
- Monitor endpoint: `https://your-app.railway.app/health`
- Alert on downtime

---

## 🐛 **Troubleshooting**

### **Common Issues:**

**1. App Won't Start**
```bash
# Check logs for startup errors
railway logs
# Common: Missing environment variables
```

**2. Supabase Connection Failed**
```bash
# Verify environment variables
railway variables
# Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
```

**3. Twilio Webhook Errors**
```bash
# Check webhook URL in Twilio Console
# Must be: https://your-app.railway.app/webhooks/twilio
# Test with: curl -X POST url
```

**4. OpenAI API Errors**
```bash
# Verify OPENAI_API_KEY is set
# Check OpenAI usage limits
```

---

## 🎯 **Success Criteria**

✅ **API responding** on `/health` and `/`  
✅ **WhatsApp messages** trigger ConciergeAgent responses  
✅ **Trip creation** sends confirmation messages  
✅ **Document API** working for uploads/retrieval  
✅ **Logs** showing structured JSON output  

---

**Ready for production!** 🚀 

Next steps after deployment:
1. Test thoroughly with real WhatsApp messages
2. Monitor logs for errors
3. Implement improvements from `docs/issues_and_improvements.md` 