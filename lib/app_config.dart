/// Where the IlocoAdal engine (the Python server) is listening.
///
/// Override when running, no code change needed:
///   flutter run -d windows \
///     --dart-define=ILOCOADAL_URL=http://127.0.0.1:8765 \
///     --dart-define=ILOCOADAL_TOKEN=my-secret
///
/// The token must match `server.auth_token` in the server's config.json
/// (leave both empty to turn it off).
class AppConfig {
  static const googleKey = String.fromEnvironment(
    'ILOCOADAL_GOOGLE_KEY',
    defaultValue: '',
  );
  static const baseUrl = String.fromEnvironment(
    'ILOCOADAL_URL',
    defaultValue: 'http://127.0.0.1:8765',
  );
  static const token = String.fromEnvironment(
    'ILOCOADAL_TOKEN',
    defaultValue: '',
  );
}
