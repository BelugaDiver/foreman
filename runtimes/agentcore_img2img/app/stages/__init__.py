# Pipeline stage implementations.
#
# Stages are pure async functions; each accepts a PipelineSettings instance
# and returns a typed result dataclass.  They have no side-effects beyond
# Bedrock model invocations.
