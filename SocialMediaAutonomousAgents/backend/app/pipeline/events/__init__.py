"""Event-sourced pipeline run tracking (NATS JetStream).

The pipeline emits typed :class:`PipelineEvent` envelopes through an in-process
:class:`EventDispatcher` (a ContextVar bus mirroring ``pipeline_progress``). Sinks
fan those events out — :class:`NatsPublishSink` publishes them to the JetStream
``PIPELINE_EVENTS`` stream, which is the durable source of truth. Consumers fold
the stream into a queryable ``PipelineRunDocument`` projection and drive the live
SSE view.
"""
