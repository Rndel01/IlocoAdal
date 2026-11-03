import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/app_theme.dart';

/// The opening animation: a solid cream screen (the native splash is the same
/// colour, so there is no flash), then the green logo fades and scales in,
/// followed by the name and a small spinner while the engine starts.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _anim = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1500),
  )..forward();

  late final Animation<double> _logoFade = CurvedAnimation(
    parent: _anim,
    curve: const Interval(0.0, 0.5, curve: Curves.easeOut),
  );
  late final Animation<double> _logoScale = Tween<double>(begin: 0.7, end: 1.0)
      .animate(
        CurvedAnimation(
          parent: _anim,
          curve: const Interval(0.0, 0.65, curve: Curves.easeOutBack),
        ),
      );
  late final Animation<double> _textFade = CurvedAnimation(
    parent: _anim,
    curve: const Interval(0.5, 1.0, curve: Curves.easeOut),
  );

  @override
  void dispose() {
    _anim.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: AppColors.cream,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: AppColors.cream,
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              FadeTransition(
                opacity: _logoFade,
                child: ScaleTransition(
                  scale: _logoScale,
                  child: Image.asset(
                    'assets/icon/icon_foreground.png',
                    width: 300,
                    height: 300,
                  ),
                ),
              ),
              FadeTransition(
                opacity: _textFade,
                child: Column(
                  children: [
                    const Text(
                      'IlocoAdal',
                      style: TextStyle(
                        color: AppColors.green,
                        fontSize: 28,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Key terms, in Ilocano',
                      style: TextStyle(color: AppColors.muted, fontSize: 13),
                    ),
                    const SizedBox(height: 28),
                    const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AppColors.green,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
