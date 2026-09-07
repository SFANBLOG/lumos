/// 合同分析状态管理 (Riverpod 版).
///
/// 使用 AsyncNotifier + StateController 管理从提交到完成的完整分析流程，
/// 支持取消、重试、订阅 SSE 流式事件。
library;

import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/contract_service.dart';
import '../api/models.dart';

/// 分析状态快照
class AnalysisSnapshot {
  final AnalysisPhase phase;
  final double progress;
  final String statusMessage;
  final String? contractId;
  final List<RiskItem> risks;
  final AnalysisSummary? summary;
  final String? errorMessage;
  final bool isAnalyzing;

  const AnalysisSnapshot({
    this.phase = AnalysisPhase.idle,
    this.progress = 0.0,
    this.statusMessage = '',
    this.contractId,
    this.risks = const [],
    this.summary,
    this.errorMessage,
    this.isAnalyzing = false,
  });

  AnalysisSnapshot copyWith({
    AnalysisPhase? phase,
    double? progress,
    String? statusMessage,
    String? contractId,
    List<RiskItem>? risks,
    AnalysisSummary? summary,
    String? errorMessage,
    bool? isAnalyzing,
  }) {
    return AnalysisSnapshot(
      phase: phase ?? this.phase,
      progress: progress ?? this.progress,
      statusMessage: statusMessage ?? this.statusMessage,
      contractId: contractId ?? this.contractId,
      risks: risks ?? this.risks,
      summary: summary ?? this.summary,
      errorMessage: errorMessage ?? this.errorMessage,
      isAnalyzing: isAnalyzing ?? this.isAnalyzing,
    );
  }
}

/// 合同分析状态 Notifier
class AnalysisNotifier extends StateNotifier<AnalysisSnapshot> {
  AnalysisNotifier() : super(const AnalysisSnapshot());

  final ContractService _service = ContractService();
  CancelToken? _cancelToken;
  StreamSubscription<SSEParsedEvent>? _sseSubscription;

  /// 当前是否正在分析中
  bool get isAnalyzing => state.isAnalyzing;

  /// 开始分析合同
  Future<void> analyzeContract(
    String text, {
    ContractSource source = ContractSource.textPaste,
  }) async {
    // 取消之前的分析
    await cancel();

    _setAnalyzing(AnalysisPhase.submitting);
    _updateState(
      statusMessage: '正在提交合同…',
      progress: 0.0,
      risks: [],
      summary: null,
      errorMessage: null,
    );

    _cancelToken = CancelToken();

    try {
      final response = await _service.submitContract(
        text: text,
        source: source,
        cancelToken: _cancelToken,
      );

      _updateState(
        contractId: response.contractId,
        statusMessage: response.message,
      );

      await _subscribeSSE(response.contractId);
    } catch (e) {
      _setError('提交失败: $e');
    }
  }

  /// 重试分析
  Future<void> retry(String text, {ContractSource source = ContractSource.textPaste}) async {
    await analyzeContract(text, source: source);
  }

  /// 取消当前分析
  Future<void> cancel() async {
    if (_cancelToken != null && !_cancelToken!.isCancelled) {
      _cancelToken!.cancel('用户取消分析');
    }
    await _sseSubscription?.cancel();
    _sseSubscription = null;
    _cancelToken = null;
  }

  /// 重置状态
  Future<void> reset() async {
    await cancel();
    state = const AnalysisSnapshot();
  }

  Future<void> _subscribeSSE(String contractId) async {
    _cancelToken = CancelToken();

    final stream = _service.streamAnalysis(
      contractId,
      cancelToken: _cancelToken,
    );

    _sseSubscription = stream.listen(
      _handleSSEEvent,
      onError: (Object error) {
        _setError('SSE 流异常: $error');
      },
      onDone: () {
        if (state.phase != AnalysisPhase.error) {
          _updateState(
            phase: AnalysisPhase.completed,
            progress: 1.0,
            isAnalyzing: false,
          );
        }
      },
    );
  }

  void _handleSSEEvent(SSEParsedEvent event) {
    switch (event.type) {
      case SSEEventType.nodeStart:
        final nodeProgress = AgentNodeProgress.fromJson(event.data);
        _updateState(
          progress: nodeProgress.progress,
          statusMessage: nodeProgress.description,
          phase: _phaseFromNodeName(nodeProgress.nodeName),
        );
        break;

      case SSEEventType.nodeComplete:
        final nodeProgress = AgentNodeProgress.fromJson(event.data);
        _updateState(
          progress: nodeProgress.progress,
          statusMessage: nodeProgress.description,
        );
        break;

      case SSEEventType.thinking:
        _updateState(
          statusMessage: event.data['message'] as String? ?? '思考中…',
        );
        break;

      case SSEEventType.riskFound:
        final risk = RiskItem.fromJson(event.data);
        _updateState(risks: [...state.risks, risk]);
        break;

      case SSEEventType.summary:
        final summary = AnalysisSummary.fromJson(event.data);
        _updateState(summary: summary);
        break;

      case SSEEventType.complete:
        _updateState(
          phase: AnalysisPhase.completed,
          progress: 1.0,
          statusMessage: event.data['message'] as String? ?? '分析完成',
          isAnalyzing: false,
        );
        break;

      case SSEEventType.error:
        _setError(event.data['message'] as String? ?? '未知错误');
        break;
    }
  }

  void _setAnalyzing(AnalysisPhase phase) {
    state = state.copyWith(
      phase: phase,
      isAnalyzing: true,
      errorMessage: null,
    );
  }

  void _setError(String message) {
    state = state.copyWith(
      phase: AnalysisPhase.error,
      errorMessage: message,
      isAnalyzing: false,
    );
  }

  void _updateState({
    AnalysisPhase? phase,
    double? progress,
    String? statusMessage,
    String? contractId,
    List<RiskItem>? risks,
    AnalysisSummary? summary,
    String? errorMessage,
    bool? isAnalyzing,
  }) {
    state = state.copyWith(
      phase: phase ?? state.phase,
      progress: progress ?? state.progress,
      statusMessage: statusMessage ?? state.statusMessage,
      contractId: contractId ?? state.contractId,
      risks: risks ?? state.risks,
      summary: summary ?? state.summary,
      errorMessage: errorMessage ?? state.errorMessage,
      isAnalyzing: isAnalyzing ?? state.isAnalyzing,
    );
  }

  AnalysisPhase _phaseFromNodeName(String name) {
    return switch (name) {
      'extractor' => AnalysisPhase.extracting,
      'retriever' => AnalysisPhase.retrieving,
      'reviewer' => AnalysisPhase.reviewing,
      'negotiator' => AnalysisPhase.negotiating,
      _ => state.phase,
    };
  }

  @override
  void dispose() {
    cancel();
    super.dispose();
  }
}

/// 全局 AnalysisProvider
final analysisProvider = StateNotifierProvider<AnalysisNotifier, AnalysisSnapshot>(
  (ref) => AnalysisNotifier(),
);
