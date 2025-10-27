import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

// Set your deployed URL via --dart-define=INITIAL_URL=...
const String kDefaultUrl = String.fromEnvironment(
  'INITIAL_URL',
  defaultValue: 'http://127.0.0.1:5231',
);

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'YouTube Downloader',
      theme: ThemeData.dark(),
      home: const WebShell(),
    );
  }
}

class WebShell extends StatefulWidget {
  const WebShell({super.key});
  @override
  State<WebShell> createState() => _WebShellState();
}

class _WebShellState extends State<WebShell> {
  late final WebViewController _controller;
  String currentUrl = kDefaultUrl;
  bool canBack = false;
  bool canForward = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (_) async {
            final b = await _controller.canGoBack();
            final f = await _controller.canGoForward();
            setState(() { canBack = b; canForward = f; });
          },
        ),
      )
      ..loadRequest(Uri.parse(currentUrl));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('YouTube Downloader'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => _controller.reload(),
          ),
        ],
      ),
      body: SafeArea(child: WebViewWidget(controller: _controller)),
      bottomNavigationBar: SafeArea(
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            IconButton(
              icon: const Icon(Icons.arrow_back),
              onPressed: canBack ? () => _controller.goBack() : null,
            ),
            IconButton(
              icon: const Icon(Icons.home),
              onPressed: () => _controller.loadRequest(Uri.parse(kDefaultUrl)),
            ),
            IconButton(
              icon: const Icon(Icons.arrow_forward),
              onPressed: canForward ? () => _controller.goForward() : null,
            ),
          ],
        ),
      ),
    );
  }
}
