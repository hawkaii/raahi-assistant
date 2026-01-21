#!/usr/bin/env python3
"""
Test script for the Raahi Assistant API
Tests the /assistant/query-with-audio endpoint and saves audio to output.wav
"""

import json
import sys
import subprocess
from pathlib import Path

# API configuration
API_BASE_URL = "http://localhost:8000"
QUERY_WITH_AUDIO_ENDPOINT = f"{API_BASE_URL}/assistant/query-with-audio"

# Default test data
DEFAULT_REQUEST = {
    "text": "Delhi se Mumbai ka duty chahiye",
    "driver_profile": {
        "id": "123",
        "name": "Rajesh",
        "phone": "+919876543210",
        "is_verified": False,
        "vehicle_type": "Container"
    },
    "current_location": {
        "latitude": 28.6139,
        "longitude": 77.2090
    }
}


def test_query_with_audio(request_data=None, output_file="output.wav"):
    """
    Test the /assistant/query-with-audio endpoint
    
    Args:
        request_data: Custom request payload (uses default if None)
        output_file: Path to save audio output (default: output.wav)
    
    Returns:
        Tuple of (response_json, audio_file_path)
    """
    if request_data is None:
        request_data = DEFAULT_REQUEST
    
    print("=" * 60)
    print("Testing /assistant/query-with-audio endpoint")
    print("=" * 60)
    print(f"\nRequest Text: {request_data['text']}")
    print(f"Driver: {request_data['driver_profile']['name']}\n")
    
    try:
        # Step 1: Call API using curl
        print("1. Calling /assistant/query-with-audio...")
        
        import subprocess
        import tempfile
        
        # Create temp file for request JSON
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(request_data, f)
            request_file = f.name
        
        # Call curl to get response
        response_file = '/tmp/response.bin'
        curl_cmd = [
            'curl', '-s', '-X', 'POST',
            QUERY_WITH_AUDIO_ENDPOINT,
            '-H', 'Content-Type: application/json',
            '-d', f'@{request_file}',
            '-o', response_file
        ]
        
        result = subprocess.run(curl_cmd, capture_output=True, text=True)

        # Clean up temp request file
        Path(request_file).unlink()

        if result.returncode != 0:
            print(f"   ✗ Error calling API: {result.stderr}")
            print(f"   Return code: {result.returncode}")
            print(f"   Stdout: {result.stdout}")
            return None, None
        
        print(f"   ✓ Response received")
        
        # Step 2: Parse response
        print(f"\n2. Parsing response...")
        
        with open(response_file, 'rb') as f:
            data = f.read()
        
        # Find the JSON-audio boundary (first newline after JSON)
        json_end = data.find(b'\n')
        
        if json_end == -1:
            print(f"   ✗ Invalid response format (no JSON found)")
            return None, None
        
        json_str = data[:json_end].decode('utf-8')
        audio_data = data[json_end+1:]
        
        # Parse and display JSON
        response = json.loads(json_str)
        print(f"   ✓ Parsed JSON response")
        
        print(f"\n3. API Response:")
        print(f"   Session ID: {response.get('session_id')}")
        print(f"   Intent: {response.get('intent')}")
        print(f"   UI Action: {response.get('ui_action')}")
        print(f"   Response Text: {response.get('response_text')}")
        print(f"   Audio Cached: {response.get('audio_cached')}")
        print(f"   Cache Key: {response.get('cache_key')}")
        print(f"   Audio URL: {response.get('audio_url')}")
        print(f"   Audio Data: {len(audio_data)} bytes")
        
        # If GET_DUTIES intent, display query and counts
        if response.get('intent') == 'get_duties' and response.get('data'):
            data = response['data']
            print(f"\n   📊 Duty Search Results:")
            
            # Display query metadata
            query = data.get('query', {})
            print(f"      Query:")
            print(f"        • Pickup City: {query.get('pickup_city')}")
            print(f"        • Drop City: {query.get('drop_city')}")
            print(f"        • Used Geocoding: {query.get('used_geo')}")
            
            # Display counts
            counts = data.get('counts', {})
            print(f"      Counts:")
            print(f"        • Trips: {counts.get('trips')}")
            print(f"        • Leads: {counts.get('leads')}")
            print(f"        • Total: {counts.get('total')}")
            
            # Display city names extracted
            city_names = data.get('city_names', [])
            print(f"      Extracted Cities: {', '.join(city_names) if city_names else 'None'}")
            
            # Show sample duties
            duties = data.get('duties', [])
            if duties:
                print(f"\n   📋 Sample Duties (showing first 3):")
                for i, duty in enumerate(duties[:3], 1):
                    duty_type = duty.get('type', 'unknown').upper()
                    pickup = duty.get('pickup_city', 'N/A')
                    drop = duty.get('drop_city', 'N/A')
                    status = duty.get('status', 'N/A')
                    print(f"      {i}. [{duty_type}] {pickup} → {drop} (Status: {status})")
                    if duty.get('type') == 'trip':
                        trip_type = duty.get('trip_type', 'N/A')
                        print(f"         Trip Type: {trip_type}")
            else:
                print(f"\n   ⚠️  No duties found")
        
        # Check if audio_url is provided (for entry state or GET_DUTIES)
        if response.get('audio_url'):
            print(f"\n   ℹ️  Audio URL provided (no streaming): {response.get('audio_url')}")
            print(f"\n" + "=" * 60)
            print("✓ Test completed successfully (Audio via URL)!")
            print("=" * 60)
            return response, None
        
        if len(audio_data) == 0:
            print(f"\n   ✗ No audio data received and no audio_url")
            return response, None
        
        # Step 3: Save MP3 first
        print(f"\n4. Saving audio...")
        temp_mp3 = '/tmp/temp_audio.mp3'
        with open(temp_mp3, 'wb') as f:
            f.write(audio_data)
        print(f"   ✓ Saved MP3 ({len(audio_data)} bytes)")
        
        # Step 4: Convert to WAV using ffmpeg
        print(f"\n5. Converting to WAV...")
        try:
            subprocess.run(
                ['ffmpeg', '-i', temp_mp3, '-acodec', 'pcm_s16le', 
                 '-ar', '16000', output_file, '-y'],
                capture_output=True,
                check=True
            )
            file_size = Path(output_file).stat().st_size
            print(f"   ✓ Converted to WAV")
            print(f"   File: {output_file}")
            print(f"   Size: {file_size / 1024:.2f} KB")
            
        except subprocess.CalledProcessError as e:
            print(f"   ✗ FFmpeg conversion failed: {e.stderr.decode()}")
            # Fallback: save as MP3
            mp3_file = output_file.replace('.wav', '.mp3')
            with open(mp3_file, 'wb') as f:
                f.write(audio_data)
            print(f"   → Saved as MP3 instead: {mp3_file}")
            return response, mp3_file
            
        except FileNotFoundError:
            print(f"   ✗ FFmpeg not found. Install with: apt-get install ffmpeg")
            # Fallback: save as MP3
            mp3_file = output_file.replace('.wav', '.mp3')
            with open(mp3_file, 'wb') as f:
                f.write(audio_data)
            print(f"   → Saved as MP3 instead: {mp3_file}")
            return response, mp3_file
        
        print("\n" + "=" * 60)
        print("✓ Test completed successfully!")
        print("=" * 60)
        
        return response, output_file
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test Raahi Assistant API and save audio output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  .venv/bin/python test_api_query.py
  .venv/bin/python test_api_query.py --text "Paas mein CNG pump kahan hai?" --output fuel_station.wav
  .venv/bin/python test_api_query.py --text "Mera profile verify kaise hoga?" --output profile.wav
        """
    )
    
    parser.add_argument(
        '--text',
        type=str,
        default=DEFAULT_REQUEST['text'],
        help='Query text to send to the API'
    )
    parser.add_argument(
        '--id',
        type=str,
        default=DEFAULT_REQUEST['driver_profile']['id'],
        help='Driver ID'
    )
    parser.add_argument(
        '--driver-name',
        type=str,
        default=DEFAULT_REQUEST['driver_profile']['name'],
        help='Driver name'
    )
    parser.add_argument(
        '--latitude',
        type=float,
        default=DEFAULT_REQUEST['current_location']['latitude'],
        help='Current latitude'
    )
    parser.add_argument(
        '--longitude',
        type=float,
        default=DEFAULT_REQUEST['current_location']['longitude'],
        help='Current longitude'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='output.wav',
        help='Output audio file path (default: output.wav)'
    )
    parser.add_argument(
        '--url',
        type=str,
        default=API_BASE_URL,
        help=f'API base URL (default: {API_BASE_URL})'
    )
    
    args = parser.parse_args()
    
    # Build request
    request_data = {
        "text": args.text,
        "driver_profile": {
            "id": args.id,
            "name": args.driver_name,
            "phone": "+919876543210",
            "is_verified": False,
            "vehicle_type": "Container"
        },
        "current_location": {
            "latitude": args.latitude,
            "longitude": args.longitude
        }
    }
    
    # Update API URL if provided
    global QUERY_WITH_AUDIO_ENDPOINT
    QUERY_WITH_AUDIO_ENDPOINT = f"{args.url}/assistant/query-with-audio"
    
    # Test the API
    response_json, audio_file = test_query_with_audio(request_data, args.output)
    
    if not audio_file:
        sys.exit(1)


if __name__ == "__main__":
    main()
