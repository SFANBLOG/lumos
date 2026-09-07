/// MCP 工具调用结果页.
///
/// 为简单参数提供输入表单，调用工具并展示返回结果。
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api/mcp_service.dart';

class MCPToolResultScreen extends StatefulWidget {
  final String toolName;

  const MCPToolResultScreen({super.key, required this.toolName});

  @override
  State<MCPToolResultScreen> createState() => _MCPToolResultScreenState();
}

class _MCPToolResultScreenState extends State<MCPToolResultScreen> {
  final MCPService _mcpService = MCPService();
  final Map<String, TextEditingController> _controllers = {};
  String? _result;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Widget _buildArgumentFields() {
    return Column(
      children: _controllers.entries.map((entry) {
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: TextField(
            controller: entry.value,
            decoration: InputDecoration(
              labelText: entry.key,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        );
      }).toList(),
    );
  }

  Future<void> _callTool() async {
    final arguments = <String, dynamic>{};
    for (final entry in _controllers.entries) {
      final value = entry.value.text.trim();
      if (value.isEmpty) {
        setState(() => _error = '${entry.key} 不能为空');
        return;
      }
      arguments[entry.key] = value;
    }

    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });

    try {
      final response = await _mcpService.callTool(
        name: widget.toolName,
        arguments: arguments,
      );
      setState(() {
        _result = const JsonEncoder.withIndent('  ').convert(response.result);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = '调用失败: $e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    // 初始化默认参数表单 (简化版)
    if (_controllers.isEmpty) {
      _controllers['query'] = TextEditingController();
    }

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
          widget.toolName,
          style: GoogleFonts.notoSansSc(
            fontWeight: FontWeight.w700,
            color: theme.colorScheme.onSurface,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          _buildArgumentFields(),
          const SizedBox(height: 20),
          CupertinoButton.filled(
            borderRadius: BorderRadius.circular(12),
            onPressed: _loading ? null : _callTool,
            child: _loading
                ? const CupertinoActivityIndicator(color: Colors.white)
                : Text(
                    '调用',
                    style: GoogleFonts.notoSansSc(fontWeight: FontWeight.w600),
                  ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 16),
            Text(
              _error!,
              style: GoogleFonts.notoSansSc(color: theme.colorScheme.error),
            ),
          ],
          if (_result != null) ...[
            const SizedBox(height: 24),
            Row(
              children: [
                Text(
                  '返回结果',
                  style: GoogleFonts.notoSansSc(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const Spacer(),
                IconButton(
                  icon: const Icon(CupertinoIcons.doc_on_doc),
                  onPressed: () {
                    Clipboard.setData(ClipboardData(text: _result!));
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('结果已复制')),
                    );
                  },
                ),
              ],
            ),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.04),
                borderRadius: BorderRadius.circular(12),
              ),
              child: SelectableText(
                _result!,
                style: GoogleFonts.notoSansSc(
                  fontSize: 13,
                  height: 1.5,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
