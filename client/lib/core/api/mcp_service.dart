/// MCP 工具服务.
///
/// 调用后端 /api/v1/mcp 接口，列出并调用 MCP 工具。
library;

import 'package:dio/dio.dart';

import 'api_client.dart';
import 'models.dart';

/// MCP 服务
class MCPService {
  final Dio _dio = apiClient;

  /// 列出所有可用的 MCP 工具
  Future<List<MCPTool>> listTools({CancelToken? cancelToken}) async {
    final response = await _dio.get(
      '/mcp/tools',
      cancelToken: cancelToken,
    );

    final list = response.data as List<dynamic>;
    return list
        .map((e) => MCPTool.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 调用指定的 MCP 工具
  Future<MCPToolCallResponse> callTool({
    required String name,
    required Map<String, dynamic> arguments,
    CancelToken? cancelToken,
  }) async {
    final request = MCPToolCallRequest(
      toolName: name,
      arguments: arguments,
    );

    final response = await _dio.post(
      '/mcp/tools/call',
      data: request.toJson(),
      cancelToken: cancelToken,
    );

    return MCPToolCallResponse.fromJson(response.data as Map<String, dynamic>);
  }
}
