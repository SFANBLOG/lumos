/// 合同分析状态管理 (兼容层).
///
/// 保留原有 ChangeNotifier 接口供老代码使用，
/// 内部转发到 Riverpod 的 [AnalysisNotifier]。
/// 新项目请直接使用 [core/providers/analysis_provider.dart]。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/models.dart';
import '../../core/providers/analysis_provider.dart';

/// 分析状态
///
/// 已迁移到 [AnalysisNotifier]，此处仅作为兼容层。
class AnalysisState extends ChangeNotifier {
  final AnalysisNotifier _notifier;
  AnalysisSnapshot? _lastSnapshot;

  AnalysisState(Ref ref) : _notifier = ref.read(analysisProvider.notifier) {
    _notifier.addListener(_onSnapshotChanged);
  }

  AnalysisPhase get phase => _lastSnapshot?.phase ?? AnalysisPhase.idle;
  double get progress => _lastSnapshot?.progress ?? 0.0;
  String get statusMessage => _lastSnapshot?.statusMessage ?? '';
  String? get contractId => _lastSnapshot?.contractId;
  List<RiskItem> get risks => _lastSnapshot?.risks ?? [];
  AnalysisSummary? get summary => _lastSnapshot?.summary;
  String? get errorMessage => _lastSnapshot?.errorMessage;
  bool get isAnalyzing => _lastSnapshot?.isAnalyzing ?? false;

  Future<void> analyzeContract(String text, {ContractSource source = ContractSource.textPaste}) async {
    await _notifier.analyzeContract(text, source: source);
  }

  Future<void> retry(String text, {ContractSource source = ContractSource.textPaste}) async {
    await _notifier.retry(text, source: source);
  }

  Future<void> reset() async {
    await _notifier.reset();
  }

  Future<void> cancel() async {
    await _notifier.cancel();
  }

  void _onSnapshotChanged(AnalysisSnapshot snapshot) {
    _lastSnapshot = snapshot;
    notifyListeners();
  }

  @override
  void dispose() {
    _notifier.removeListener(_onSnapshotChanged);
    super.dispose();
  }
}
