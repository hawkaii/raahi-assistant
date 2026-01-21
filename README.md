# Raahi AI Assistant

A Python backend for a voice-enabled AI assistant for truck drivers, featuring:

- **Vertex AI Gemini** for intent classification and response generation
- **Typesense** for searching duties/trips and nearby fuel stations
- **Google Cloud TTS** with Chirp 3 HD (Aoede voice) for natural speech
- **Redis** for audio caching
- **FastAPI** with chunked transfer encoding for audio streaming

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              Client Application (Mobile/Web)                     │
│                                                                  │
│  Any client technology can integrate via HTTP API:              │
│  • Flutter/React Native (mobile apps)                           │
│  • React/Vue/Angular (web apps)                                 │
│  • Native iOS (Swift) / Android (Kotlin)                        │
│                                                                  │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────────────┐  │
│  │ Speech-to-   │  │   UI with   │  │   Audio Player        │  │
│  │    Text      │──│  Actions    │──│   (any lib/SDK)       │  │
│  └──────────────┘  └─────────────┘  └───────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP POST (text + context)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  POST /assistant/query-with-audio                         │  │
│  │  - Returns JSON metadata (first line)                     │  │
│  │  - Streams MP3 audio (chunked transfer)                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│            │                    │                    │          │
│            ▼                    ▼                    ▼          │
│  ┌─────────────┐    ┌──────────────────┐    ┌─────────────┐   │
│  │   Gemini    │    │    Typesense     │    │  Cloud TTS  │   │
│  │  (Intent +  │    │   (Geo Search)   │    │  Chirp 3 HD │   │
│  │  Response)  │    │                  │    │   (Aoede)   │   │
│  └─────────────┘    └──────────────────┘    └─────────────┘   │
│                                                      │          │
│                              ┌────────────────────────┘          │
│                              ▼                                   │
│                     ┌─────────────┐                             │
│                     │    Redis    │                             │
│                     │ (Audio      │                             │
│                     │  Cache)     │                             │
│                     └─────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

## Features

### 1. Get Duties
Search for available trips/cargo between cities.
- Intent: `get_duties`
- UI Action: `show_duties_list`
- Example: "Delhi se Mumbai ka duty chahiye"

### 2. Nearby CNG/Petrol Pumps
Find fuel stations near current location using geo-search.
- Intent: `cng_pumps` or `petrol_pumps`
- UI Action: `show_cng_stations` or `show_petrol_stations`
- Example: "Paas mein CNG pump kahan hai?"

### 3. Profile Verification
Help drivers verify their profiles and documents.
- Intent: `profile_verification`
- UI Action: `show_verification_checklist`
- Example: "Mera profile verify kaise hoga?"

### 4. Generic/Fallback
Handle unrecognized queries gracefully.
- Intent: `generic`
- UI Action: `none`

## API Endpoints

### POST /assistant/query
Returns JSON response without audio. Use when you want to control audio playback separately.

```json
{
  "text": "Delhi se Mumbai ka duty chahiye",
  "driver_profile": {
    "id": "123",
    "name": "Rajesh",
    "phone": "+919876543210",
    "is_verified": false,
    "vehicle_type": "Container"
  },
  "current_location": {
    "latitude": 28.6139,
    "longitude": 77.2090
  }
}
```

Response:
```json
{
  "session_id": "uuid",
  "intent": "get_duties",
  "ui_action": "show_duties_list",
  "response_text": "Delhi se Mumbai ke liye duties...",
  "data": {
    "duties": [...]
  },
  "audio_cached": true,
  "cache_key": "tts:abc123"
}
```

### GET /assistant/audio/{cache_key}
Stream cached audio. Returns 404 if not cached.

### POST /assistant/query-with-audio
Returns JSON + streams audio in single response (chunked transfer encoding).

Response format:
```
{"session_id":"...","intent":"...","ui_action":"...","response_text":"...","data":{...}}
<binary audio data - MP3>
```

## Setup

### Option 1: Docker (Recommended)

The easiest way to run the application with all dependencies:

#### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required environment variables:
- `GCP_PROJECT_ID`: Your Google Cloud project
- `TYPESENSE_API_KEY`: Typesense API key (will be used by the container)
- Optional: `GOOGLE_APPLICATION_CREDENTIALS`: Path to GCP service account JSON file

#### 2. Start All Services

```bash
# Start all services (FastAPI, Redis, Typesense)
docker-compose up -d

# View logs
docker-compose logs -f raahi-assistant

# Check service status
docker-compose ps
```

#### 3. Setup Typesense Collections

```bash
# Run setup script inside the container
docker-compose exec raahi-assistant python scripts/setup_typesense.py
```

#### 4. Access the API

- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Typesense: http://localhost:8108
- Redis: localhost:6379

#### Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v
```

### Option 2: Local Development

For local development without Docker:

#### 1. Install Dependencies

```bash
cd raahi_assistant
pip install -e .
```

#### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required:
- `GCP_PROJECT_ID`: Your Google Cloud project
- `TYPESENSE_API_KEY`: Typesense API key
- `REDIS_URL`: Redis connection URL (default: redis://localhost:6379)

**Note**: You need to run Redis and Typesense separately:

```bash
# Run Redis (using Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Run Typesense (using Docker)
docker run -d -p 8108:8108 \
  -e TYPESENSE_API_KEY=your-api-key \
  typesense/typesense:26.0
```

#### 3. Setup Typesense Collections

```bash
python scripts/setup_typesense.py
```

#### 4. Run the Server

```bash
uvicorn app.main:app --reload
```

## Client Integration

The Raahi AI Assistant API can be integrated with any client technology that supports HTTP requests and audio playback.

### Integration Steps

#### 1. Capture User Voice Input
Use any speech-to-text library appropriate for your platform:
- **Mobile (Flutter)**: `speech_to_text` package
- **Mobile (React Native)**: `@react-native-voice/voice` or `expo-speech`
- **iOS Native**: `Speech` framework (`SFSpeechRecognizer`)
- **Android Native**: `SpeechRecognizer` API
- **Web**: Web Speech API (`SpeechRecognition`)

#### 2. Send Request to API
Make HTTP POST request to `/assistant/query` or `/assistant/query-with-audio`:

```json
{
  "text": "Delhi se Mumbai ka duty chahiye",
  "driver_profile": {
    "id": "123",
    "name": "Rajesh",
    "phone": "+919876543210",
    "is_verified": false,
    "vehicle_type": "Container"
  },
  "current_location": {
    "latitude": 28.6139,
    "longitude": 77.2090
  }
}
```

#### 3. Parse Response for UI Actions
The API returns a `ui_action` field indicating what the client should display:
- `show_duties_list` → Navigate to duties/trips list screen
- `show_cng_stations` → Show CNG pump map/list
- `show_petrol_stations` → Show petrol pump map/list
- `show_verification_checklist` → Open profile verification flow
- `none` → Just display text response

#### 4. Play Audio Response

**Option A: Using `/query-with-audio` (Recommended)**
- Receives JSON metadata on first line, then streamed MP3 audio
- Parse first line for UI action
- Pipe remaining bytes to audio player

**Option B: Using `/query` + `/audio/{cache_key}`**
- Get JSON response with `cache_key`
- Fetch audio separately if `audio_cached` is true
- More control over audio playback timing

### Example Implementations

#### Flutter Example
```dart
import 'package:http/http.dart' as http;
import 'package:just_audio/just_audio.dart';

// Send request
final response = await http.post(
  Uri.parse('$baseUrl/assistant/query'),
  body: jsonEncode(request),
);

final data = jsonDecode(response.body);

// Handle UI action
if (data['ui_action'] == 'show_duties_list') {
  Navigator.push(context, DutiesListScreen(data['data']));
}

// Play audio if cached
if (data['audio_cached']) {
  await audioPlayer.setUrl('$baseUrl/assistant/audio/${data['cache_key']}');
  audioPlayer.play();
}
```

#### React Native Example
```javascript
import axios from 'axios';
import Sound from 'react-native-sound';

// Send request
const { data } = await axios.post(`${baseUrl}/assistant/query`, request);

// Handle UI action
if (data.ui_action === 'show_duties_list') {
  navigation.navigate('DutiesList', { data: data.data });
}

// Play audio
if (data.audio_cached) {
  const sound = new Sound(`${baseUrl}/assistant/audio/${data.cache_key}`);
  sound.play();
}
```

#### Native iOS (Swift) Example
```swift
import AVFoundation

// Send request
let task = URLSession.shared.dataTask(with: request) { data, response, error in
    let json = try JSONDecoder().decode(AssistantResponse.self, from: data)
    
    // Handle UI action
    if json.uiAction == "show_duties_list" {
        DispatchQueue.main.async {
            self.showDutiesList(json.data)
        }
    }
    
    // Play audio
    if let cacheKey = json.cacheKey {
        let audioURL = URL(string: "\(baseURL)/assistant/audio/\(cacheKey)")!
        let player = AVPlayer(url: audioURL)
        player.play()
    }
}
task.resume()
```

### Key Integration Points

1. **Speech Input**: Use platform-appropriate SDK for voice recognition
2. **HTTP Client**: Standard REST API calls (POST with JSON body)
3. **UI Actions**: Parse `ui_action` field to determine screen navigation
4. **Audio Playback**: Stream or fetch MP3 audio from response
5. **Location**: Send current GPS coordinates for geo-based queries (fuel stations)
6. **Profile Context**: Include driver profile for personalized responses

## Audio Caching

Audio responses are cached in Redis:
- Cache key is derived from response text hash
- Default TTL: 7 days
- Reduces TTS API calls for repeated responses
- Generic fallback responses are cached for reuse

## Voice Configuration

Using Google Cloud TTS Chirp 3 HD:
- Voice: `en-US-Chirp3-HD-Aoede`
- High-quality, natural-sounding voice
- Supports multiple languages (configure `TTS_LANGUAGE_CODE`)

## Project Structure

```
raahi_assistant/
├── app/
│   ├── api/
│   │   └── routes.py          # FastAPI endpoints
│   ├── models/
│   │   └── schemas.py         # Pydantic models
│   ├── services/
│   │   ├── gemini_service.py  # Vertex AI Gemini
│   │   ├── typesense_service.py
│   │   ├── tts_service.py     # Cloud TTS
│   │   └── cache_service.py   # Redis caching
│   └── main.py                # FastAPI app
├── config/
│   └── settings.py            # Configuration
├── scripts/
│   └── setup_typesense.py     # Collection setup
├── pyproject.toml
└── .env.example
```
