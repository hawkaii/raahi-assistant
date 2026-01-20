/// Flutter client example for Raahi AI Assistant API
/// 
/// This demonstrates how to:
/// 1. Send transcribed text to the API
/// 2. Parse the JSON response for UI actions
/// 3. Stream and play the audio response
/// 
/// Dependencies to add to pubspec.yaml:
/// ```yaml
/// dependencies:
///   http: ^1.1.0
///   just_audio: ^0.9.36
///   speech_to_text: ^6.6.0
///   path_provider: ^2.1.1
/// ```

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// Request model matching the Python API
class AssistantRequest {
  final String text;
  final DriverProfile driverProfile;
  final Location currentLocation;
  final String? sessionId;
  final String preferredLanguage;

  AssistantRequest({
    required this.text,
    required this.driverProfile,
    required this.currentLocation,
    this.sessionId,
    this.preferredLanguage = 'en',
  });

  Map<String, dynamic> toJson() => {
        'text': text,
        'driver_profile': driverProfile.toJson(),
        'current_location': currentLocation.toJson(),
        if (sessionId != null) 'session_id': sessionId,
        'preferred_language': preferredLanguage,
      };
}

class DriverProfile {
  final String driverId;
  final String name;
  final String phone;
  final bool isVerified;
  final List<String> documentsPending;
  final String? vehicleType;
  final String? vehicleNumber;
  final bool licenseVerified;
  final bool rcVerified;
  final bool insuranceVerified;

  DriverProfile({
    required this.driverId,
    required this.name,
    required this.phone,
    this.isVerified = false,
    this.documentsPending = const [],
    this.vehicleType,
    this.vehicleNumber,
    this.licenseVerified = false,
    this.rcVerified = false,
    this.insuranceVerified = false,
  });

  Map<String, dynamic> toJson() => {
        'driver_id': driverId,
        'name': name,
        'phone': phone,
        'is_verified': isVerified,
        'documents_pending': documentsPending,
        'vehicle_type': vehicleType,
        'vehicle_number': vehicleNumber,
        'license_verified': licenseVerified,
        'rc_verified': rcVerified,
        'insurance_verified': insuranceVerified,
      };
}

class Location {
  final double latitude;
  final double longitude;

  Location({required this.latitude, required this.longitude});

  Map<String, dynamic> toJson() => {
        'latitude': latitude,
        'longitude': longitude,
      };
}

/// Response model matching the Python API
class AssistantResponse {
  final String sessionId;
  final String intent;
  final String uiAction;
  final String responseText;
  final Map<String, dynamic>? data;
  final bool audioCached;
  final String? cacheKey;

  AssistantResponse({
    required this.sessionId,
    required this.intent,
    required this.uiAction,
    required this.responseText,
    this.data,
    required this.audioCached,
    this.cacheKey,
  });

  factory AssistantResponse.fromJson(Map<String, dynamic> json) {
    return AssistantResponse(
      sessionId: json['session_id'],
      intent: json['intent'],
      uiAction: json['ui_action'],
      responseText: json['response_text'],
      data: json['data'],
      audioCached: json['audio_cached'] ?? false,
      cacheKey: json['cache_key'],
    );
  }
}

/// UI Actions enum matching Python API
enum UIAction {
  showDutiesList,
  showCngStations,
  showPetrolStations,
  showVerificationChecklist,
  showDocumentUpload,
  navigateToProfile,
  showMap,
  none,
}

UIAction parseUIAction(String action) {
  switch (action) {
    case 'show_duties_list':
      return UIAction.showDutiesList;
    case 'show_cng_stations':
      return UIAction.showCngStations;
    case 'show_petrol_stations':
      return UIAction.showPetrolStations;
    case 'show_verification_checklist':
      return UIAction.showVerificationChecklist;
    case 'show_document_upload':
      return UIAction.showDocumentUpload;
    case 'navigate_to_profile':
      return UIAction.navigateToProfile;
    case 'show_map':
      return UIAction.showMap;
    default:
      return UIAction.none;
  }
}

/// Main client class for interacting with the Raahi Assistant API
class RaahiAssistantClient {
  final String baseUrl;
  final http.Client _client;
  String? _sessionId;

  RaahiAssistantClient({
    required this.baseUrl,
    http.Client? client,
  }) : _client = client ?? http.Client();

  String? get sessionId => _sessionId;

  /// Option 1: Query only (get JSON response, fetch audio separately)
  /// Use this when you want more control over audio playback
  Future<AssistantResponse> query(AssistantRequest request) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/assistant/query'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(request.toJson()),
    );

    if (response.statusCode != 200) {
      throw Exception('API error: ${response.statusCode}');
    }

    final data = jsonDecode(response.body);
    final assistantResponse = AssistantResponse.fromJson(data);
    _sessionId = assistantResponse.sessionId;
    return assistantResponse;
  }

  /// Fetch audio for a cache key (use after query())
  Future<List<int>> getAudio(String cacheKey) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/assistant/audio/$cacheKey'),
    );

    if (response.statusCode != 200) {
      throw Exception('Audio not found');
    }

    return response.bodyBytes;
  }

  /// Option 2: Query with audio streaming (recommended)
  /// Returns JSON metadata + streams audio data
  /// 
  /// Usage:
  /// ```dart
  /// final (response, audioStream) = await client.queryWithAudio(request);
  /// // Use response for UI updates
  /// handleUIAction(response.uiAction);
  /// // Play audio from stream
  /// await playAudioFromStream(audioStream);
  /// ```
  Future<(AssistantResponse, Stream<List<int>>)> queryWithAudio(
    AssistantRequest request,
  ) async {
    final httpRequest = http.Request(
      'POST',
      Uri.parse('$baseUrl/assistant/query-with-audio'),
    );
    httpRequest.headers['Content-Type'] = 'application/json';
    httpRequest.body = jsonEncode(request.toJson());

    final streamedResponse = await _client.send(httpRequest);

    if (streamedResponse.statusCode != 200) {
      throw Exception('API error: ${streamedResponse.statusCode}');
    }

    // Create a broadcast stream controller for the response
    final controller = StreamController<List<int>>.broadcast();
    AssistantResponse? assistantResponse;
    bool jsonParsed = false;
    List<int> buffer = [];

    // Process the chunked response
    streamedResponse.stream.listen(
      (chunk) {
        if (!jsonParsed) {
          // Look for newline separator between JSON and audio
          buffer.addAll(chunk);
          final newlineIndex = buffer.indexOf(10); // \n
          
          if (newlineIndex != -1) {
            // Parse JSON from first part
            final jsonBytes = buffer.sublist(0, newlineIndex);
            final jsonStr = utf8.decode(jsonBytes);
            final data = jsonDecode(jsonStr);
            assistantResponse = AssistantResponse.fromJson(data);
            _sessionId = assistantResponse!.sessionId;
            jsonParsed = true;

            // Add remaining bytes (audio) to stream
            if (newlineIndex + 1 < buffer.length) {
              controller.add(buffer.sublist(newlineIndex + 1));
            }
            buffer = [];
          }
        } else {
          // Stream audio chunks
          controller.add(chunk);
        }
      },
      onDone: () {
        controller.close();
      },
      onError: (error) {
        controller.addError(error);
      },
    );

    // Wait for JSON to be parsed
    while (assistantResponse == null) {
      await Future.delayed(const Duration(milliseconds: 10));
    }

    return (assistantResponse!, controller.stream);
  }

  /// Clear conversation session
  Future<void> clearSession() async {
    if (_sessionId == null) return;
    
    await _client.delete(
      Uri.parse('$baseUrl/assistant/session/$_sessionId'),
    );
    _sessionId = null;
  }

  void dispose() {
    _client.close();
  }
}

/// Example usage in a Flutter widget
/// 
/// ```dart
/// class AssistantScreen extends StatefulWidget {
///   @override
///   _AssistantScreenState createState() => _AssistantScreenState();
/// }
/// 
/// class _AssistantScreenState extends State<AssistantScreen> {
///   final client = RaahiAssistantClient(baseUrl: 'http://your-api-url:8000');
///   final speechToText = SpeechToText();
///   final audioPlayer = AudioPlayer();
///   
///   DriverProfile driverProfile = DriverProfile(
///     driverId: 'driver123',
///     name: 'Rajesh Kumar',
///     phone: '+919876543210',
///   );
///   
///   Location currentLocation = Location(latitude: 28.6139, longitude: 77.2090);
///   
///   List<dynamic> duties = [];
///   List<dynamic> stations = [];
///   bool isListening = false;
///   String transcribedText = '';
///   
///   Future<void> startListening() async {
///     if (!await speechToText.initialize()) return;
///     
///     setState(() => isListening = true);
///     
///     await speechToText.listen(
///       onResult: (result) {
///         setState(() => transcribedText = result.recognizedWords);
///         
///         if (result.finalResult) {
///           processQuery(transcribedText);
///         }
///       },
///       localeId: 'hi_IN', // Hindi, or 'en_IN' for English
///     );
///   }
///   
///   Future<void> processQuery(String text) async {
///     setState(() => isListening = false);
///     
///     try {
///       final request = AssistantRequest(
///         text: text,
///         driverProfile: driverProfile,
///         currentLocation: currentLocation,
///         sessionId: client.sessionId,
///       );
///       
///       // Get response with audio streaming
///       final (response, audioStream) = await client.queryWithAudio(request);
///       
///       // Handle UI action
///       handleUIAction(response);
///       
///       // Play audio
///       await playAudioFromStream(audioStream);
///       
///     } catch (e) {
///       print('Error: $e');
///     }
///   }
///   
///   void handleUIAction(AssistantResponse response) {
///     final action = parseUIAction(response.uiAction);
///     
///     setState(() {
///       switch (action) {
///         case UIAction.showDutiesList:
///           duties = response.data?['duties'] ?? [];
///           break;
///         case UIAction.showCngStations:
///         case UIAction.showPetrolStations:
///           stations = response.data?['stations'] ?? [];
///           break;
///         case UIAction.showVerificationChecklist:
///           // Show verification dialog
///           showVerificationBottomSheet(response.data?['verification']);
///           break;
///         case UIAction.navigateToProfile:
///           Navigator.pushNamed(context, '/profile');
///           break;
///         default:
///           break;
///       }
///     });
///   }
///   
///   Future<void> playAudioFromStream(Stream<List<int>> audioStream) async {
///     // Save to temp file and play
///     final tempDir = await getTemporaryDirectory();
///     final file = File('${tempDir.path}/response_audio.mp3');
///     final sink = file.openWrite();
///     
///     await for (final chunk in audioStream) {
///       sink.add(chunk);
///     }
///     await sink.close();
///     
///     await audioPlayer.setFilePath(file.path);
///     await audioPlayer.play();
///   }
///   
///   @override
///   Widget build(BuildContext context) {
///     return Scaffold(
///       appBar: AppBar(title: Text('Raahi Assistant')),
///       body: Column(
///         children: [
///           // Transcribed text display
///           Text(transcribedText),
///           
///           // Duties list
///           if (duties.isNotEmpty)
///             Expanded(
///               child: ListView.builder(
///                 itemCount: duties.length,
///                 itemBuilder: (ctx, i) => DutyCard(duty: duties[i]),
///               ),
///             ),
///           
///           // Stations list
///           if (stations.isNotEmpty)
///             Expanded(
///               child: ListView.builder(
///                 itemCount: stations.length,
///                 itemBuilder: (ctx, i) => StationCard(station: stations[i]),
///               ),
///             ),
///         ],
///       ),
///       floatingActionButton: FloatingActionButton(
///         onPressed: isListening ? null : startListening,
///         child: Icon(isListening ? Icons.mic : Icons.mic_none),
///       ),
///     );
///   }
/// }
/// ```
