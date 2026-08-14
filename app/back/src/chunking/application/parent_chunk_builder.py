from __future__ import annotations

import logging
from dataclasses import dataclass

from chunking.application.ports import TokenCounterPort
from chunking.domain.enums import StructuralBlockKind
from chunking.domain.models import ChunkingProfile, ParentChunk, SourceSpan, StructuralBlock
from chunking.infrastructure.canonical_tokenizer import CanonicalTokenizer


logger = logging.getLogger(__name__)
_PARENT_MAX_TOKENS = 1500


@dataclass(frozen=True)
class ParentChunkBuilder:
    """Groups structural blocks into deterministic semantic parents."""

    tokenizer: TokenCounterPort = CanonicalTokenizer()

    def build(
        self,
        *,
        document_id: str,
        profile: ChunkingProfile,
        blocks: tuple[StructuralBlock, ...],
    ) -> tuple[ParentChunk, ...]:
        if not blocks:
            return ()
        sections = self._split_sections(blocks)
        parents: list[ParentChunk] = []
        next_ordinal = 0
        for section in sections:
            section_parents = self._parents_for_section(
                document_id=document_id,
                profile=profile,
                section=section,
                start_ordinal=next_ordinal,
            )
            parents.extend(section_parents)
            next_ordinal += len(section_parents)
        logger.info(
            "Built semantic parents",
            extra={
                "document_id": document_id,
                "section_count": len(sections),
                "parent_count": len(parents),
            },
        )
        return tuple(parents)

    def _split_sections(self, blocks: tuple[StructuralBlock, ...]) -> tuple[tuple[StructuralBlock, ...], ...]:
        sections: list[list[StructuralBlock]] = []
        current: list[StructuralBlock] = []
        for block in blocks:
            if block.kind is StructuralBlockKind.HEADING and current:
                sections.append(current)
                current = [block]
                continue
            current.append(block)
        if current:
            sections.append(current)
        return self._merge_heading_only_sections(tuple(tuple(section) for section in sections))

    def _merge_heading_only_sections(
        self,
        sections: tuple[tuple[StructuralBlock, ...], ...],
    ) -> tuple[tuple[StructuralBlock, ...], ...]:
        merged_sections: list[tuple[StructuralBlock, ...]] = []
        heading_only_buffer: list[StructuralBlock] = []
        for section in sections:
            if self._is_heading_only_section(section):
                heading_only_buffer.extend(section)
                continue
            if heading_only_buffer:
                merged_sections.append(tuple(heading_only_buffer + list(section)))
                heading_only_buffer.clear()
                continue
            merged_sections.append(section)
        if heading_only_buffer:
            merged_sections.append(tuple(heading_only_buffer))
        return tuple(merged_sections)

    def _is_heading_only_section(self, section: tuple[StructuralBlock, ...]) -> bool:
        return len(section) == 1 and section[0].kind is StructuralBlockKind.HEADING

    def _parents_for_section(
        self,
        *,
        document_id: str,
        profile: ChunkingProfile,
        section: tuple[StructuralBlock, ...],
        start_ordinal: int,
    ) -> list[ParentChunk]:
        if self._is_atomic_section(section):
            return [
                self._make_parent(
                    document_id=document_id,
                    profile=profile,
                    ordinal=start_ordinal,
                    blocks=section,
                )
            ]

        parents: list[ParentChunk] = []
        current: list[StructuralBlock] = []
        for block in section:
            proposed = [*current, block]
            if current and self._token_count(proposed) > _PARENT_MAX_TOKENS:
                parents.append(
                    self._make_parent(
                        document_id=document_id,
                        profile=profile,
                        ordinal=start_ordinal + len(parents),
                        blocks=tuple(current),
                    )
                )
                current = [block]
                continue
            current.append(block)
        if current:
            parents.append(
                self._make_parent(
                    document_id=document_id,
                    profile=profile,
                    ordinal=start_ordinal + len(parents),
                    blocks=tuple(current),
                )
            )
        return parents

    def _is_atomic_section(self, section: tuple[StructuralBlock, ...]) -> bool:
        non_heading = tuple(
            block for block in section if block.kind is not StructuralBlockKind.HEADING
        )
        if not non_heading:
            return True
        return any(
            block.kind in {StructuralBlockKind.TABLE, StructuralBlockKind.FORM}
            for block in non_heading
        ) or self._token_count(section) <= _PARENT_MAX_TOKENS

    def _make_parent(
        self,
        *,
        document_id: str,
        profile: ChunkingProfile,
        ordinal: int,
        blocks: tuple[StructuralBlock, ...],
    ) -> ParentChunk:
        text = "\n\n".join(block.text for block in blocks)
        source_span = self._merge_source_spans(tuple(block.source_span for block in blocks))
        section_title, section_path = self._section_from_blocks(profile=profile, blocks=blocks)
        return ParentChunk.create(
            document_id=document_id,
            profile_id=profile.profile_id,
            ordinal=ordinal,
            text=text,
            source_span=source_span,
            block_ids=tuple(block.block_id for block in blocks),
            section_title=section_title,
            section_path=section_path,
        )

    def _section_from_blocks(
        self,
        *,
        profile: ChunkingProfile,
        blocks: tuple[StructuralBlock, ...],
    ) -> tuple[str | None, str | None]:
        """Derive the section title/path for a parent from its blocks' heading path.

        Opt-in: profiles without ``include_section_context`` keep both values None
        so v1 chunk identity and payloads are unchanged. Convention: use the
        deepest (longest) non-empty ``heading_path`` among the parent's blocks,
        tie-broken by first occurrence. A parent normally lives in one section, so
        all its content blocks share the same path; the longest path is the most
        specific heading that dominates the parent body.
        """
        if not profile.include_section_context:
            return None, None
        deepest: tuple[str, ...] = ()
        for block in blocks:
            if len(block.heading_path) > len(deepest):
                deepest = block.heading_path
        if not deepest:
            return None, None
        return deepest[-1], "/".join(deepest)

    def _merge_source_spans(self, spans: tuple[SourceSpan, ...]) -> SourceSpan:
        page_numbers = [
            span.page_start
            for span in spans
            if span.page_start is not None and span.page_end is not None
        ]
        page_ends = [
            span.page_end
            for span in spans
            if span.page_start is not None and span.page_end is not None
        ]
        if len(page_numbers) != len(spans):
            page_start = None
            page_end = None
        else:
            page_start = min(page_numbers)
            page_end = max(page_ends)
        return SourceSpan(
            page_start=page_start,
            page_end=page_end,
            char_start=min(span.char_start for span in spans),
            char_end=max(span.char_end for span in spans),
        )

    def _token_count(self, blocks: tuple[StructuralBlock, ...] | list[StructuralBlock]) -> int:
        return sum(self.tokenizer.count_tokens(block.text) for block in blocks)
