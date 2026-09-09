/// MCP 工具箱页面.
///
/// 列出后端所有可用的 MCP 工具，点击可调用。
library;

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api/mcp_service.dart';
import '../../core/api/models.dart';

class MCPToolsScreen extends StatefulWidget {
  const MCPToolsScreen({super.key});

  @override
  State<MCPToolsScreen> createState() => _MCPToolsScreenState();
}

class _MCPToolsScreenState extends State<MCPToolsScreen> {
  final MCPService _mcpService = MCPService();
  List<MCPTool> _tools = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadTools();
  }

  Future<void> _loadTools() async {
    try {
      final tools = await _mcpService.listTools();
      setState(() {
        _tools = tools;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = '加载失败: $e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: Icon(CupertinoIcons.chevron_back, color: theme.colorScheme.onSurface),
          onPressed: () => context.pop(),
        ),
        title: Text(
          'MCP 工具箱',
          style: GoogleFonts.notoSansSc(
            fontWeight: FontWeight.w700,
            color: theme.colorScheme.onSurface,
          ),
        ),
      ),
      body: _buildBody(theme),
    );
  }

  Widget _buildBody(ThemeData theme) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Text(
            _error!,
            textAlign: TextAlign.center,
            style: GoogleFonts.notoSansSc(color: theme.colorScheme.error),
          ),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(20),
      itemCount: _tools.length,
      itemBuilder: (context, index) {
        final tool = _tools[index];
        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            leading: CircleAvatar(
              backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.1),
              child: Icon(CupertinoIcons.wrench_fill, color: theme.colorScheme.primary),
            ),
            title: Text(
              tool.name,
              style: GoogleFonts.notoSansSc(fontWeight: FontWeight.w600),
            ),
            subtitle: Text(
              tool.description,
              style: GoogleFonts.notoSansSc(fontSize: 13, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
            ),
            trailing: const Icon(CupertinoIcons.chevron_right, size: 18),
            onTap: () => context.push('/mcp-tools/${tool.name}'),
          ),
        ).animate(delay: (100 * index).ms).fadeIn().slideX(begin: 0.02);
      },
    );
  }
}
