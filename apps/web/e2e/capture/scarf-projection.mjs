/** Independent source-to-head oracle for the native wrapped scarf fallback. */
import { fileURLToPath } from 'node:url';

const sourceUrl = name =>
  `/@fs/${fileURLToPath(new URL(`../../src/components/eyes/volume/${name}.ts`, import.meta.url)).replaceAll('\\', '/')}`;

/**
 * Return evidence; the capture owner persists it before enforcing the 0.05 px limit.
 * The expected position never reads a facet's final transform or a transformed
 * direct-head Z probe: WebKit can flatten that probe and lose the very depth under test.
 */
export async function measureScarfProjection(page, style) {
  if (!['bip', 'oscar', 'nimbo'].includes(style)) return [];
  return page.evaluate(
    async ({ style, geometryUrl, scarfUrl }) => {
      const [{ volumeProfile }, { scarfWrapFacets, scarfKnotFacets, SCARF_WRAP_SEGMENTS }] =
        await Promise.all([import(geometryUrl), import(scarfUrl)]);
      if (SCARF_WRAP_SEGMENTS !== 32) throw new Error('The reviewed garment contract is 32 facets');
      const roots = [...document.querySelectorAll('[data-live="true"] .lia-eyes')];
      const variants = roots.map(root => root.closest('[data-variant]')?.dataset.variant).sort();
      if (variants.join(',') !== 'female,male')
        throw new Error('Both native variants are required');

      const grouping = element => {
        const css = getComputedStyle(element);
        return {
          className: element.className,
          transform: css.transform,
          origin: css.transformOrigin,
          opacity: css.opacity,
          overflow: css.overflow,
          isolation: css.isolation,
          filter: css.filter,
          contain: css.contain,
          transformStyle: css.transformStyle,
          clipPath: css.clipPath,
          perspective: css.perspective,
          rotate: css.rotate,
          scale: css.scale,
          translate: css.translate,
        };
      };
      const probe = (parent, left, top) => {
        const point = document.createElement('span');
        Object.assign(point.style, {
          position: 'absolute',
          left,
          top,
          width: '0',
          height: '0',
          visibility: 'hidden',
          pointerEvents: 'none',
          margin: '0',
          padding: '0',
          border: '0',
        });
        parent.append(point);
        try {
          const box = point.getBoundingClientRect();
          return { x: box.x, y: box.y };
        } finally {
          point.remove();
        }
      };
      const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
      const frameOf = head => {
        const anchor = probe(head, '50%', '50%');
        let combined = new DOMMatrix();
        const ancestors = [];
        for (let node = head; node; node = node.parentElement) {
          const value = grouping(node);
          // The source-to-anchor relation is affine only for this orthographic
          // fallback. Independent CSS rotates/scales must be measured explicitly
          // before a future layout using them can enter this oracle.
          if (value.perspective !== 'none' || value.rotate !== 'none' || value.scale !== 'none')
            throw new Error('An unmeasured ancestor projection cannot enter the oracle');
          const matrix = new DOMMatrix(value.transform);
          if (Math.abs(matrix.m14) + Math.abs(matrix.m24) + Math.abs(matrix.m34) > 1e-12)
            throw new Error('A perspective transform cannot enter the affine oracle');
          combined = matrix.multiply(combined);
          ancestors.push(value);
        }
        const project = source => {
          // w=0 excludes every matrix translation; the measured native anchor
          // already contains layout, translations and all transform origins.
          const delta = combined.transformPoint(new DOMPoint(source.x, source.y, source.z, 0));
          return { x: anchor.x + delta.x, y: anchor.y + delta.y };
        };
        return { anchor, combined, ancestors, project };
      };
      const normalizedPoints = [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
        [0.5, 0.5],
      ];
      const measureFacet = (element, source, sourceIndex, front, fontSize, frame, patch = null) => {
        const width =
          Math.hypot(source.horizontal.x, source.horizontal.y, source.horizontal.z) * fontSize;
        const height = source.height * fontSize;
        const local = normalizedPoints.map(([u, v]) => {
          const along = u + ((patch?.shear ?? 0) * v * height) / width;
          return {
            x: (source.origin.x + source.horizontal.x * along) * fontSize,
            y: (source.origin.y + source.horizontal.y * along + source.height * v) * fontSize,
            z: (source.origin.z + source.horizontal.z * along) * fontSize,
          };
        });
        const native = normalizedPoints.map(([u, v]) =>
          probe(element, `${u * width}px`, `${v * height}px`)
        );
        const analytical = local.map(frame.project);
        const withoutSourceDepth = local.map(point => frame.project({ ...point, z: 0 }));
        const computed = getComputedStyle(element);
        const painted = getComputedStyle(element, '::before');
        const paintedDimensions = {
          left: parseFloat(painted.left),
          top: parseFloat(painted.top),
          width: parseFloat(painted.width),
          height: parseFloat(painted.height),
          transform: painted.transform,
          origin: painted.transformOrigin,
          backgroundImage: painted.backgroundImage,
          visibility: painted.visibility,
        };
        if (
          ![
            width,
            height,
            paintedDimensions.left,
            paintedDimensions.top,
            paintedDimensions.width,
            paintedDimensions.height,
          ].every(Number.isFinite)
        )
          throw new Error('Finite original painted dimensions are required');
        const overlap = patch ? 0 : 1;
        const dimensionError = Math.max(
          Math.abs(paintedDimensions.left + overlap),
          Math.abs(paintedDimensions.top),
          Math.abs(paintedDimensions.width - width - 2 * overlap),
          Math.abs(paintedDimensions.height - height)
        );
        const parents = [];
        for (
          let node = element.parentElement;
          node && node !== headParent(element);
          node = node.parentElement
        )
          parents.push(grouping(node));
        return {
          sourceIndex,
          front,
          sourceGeometry: source,
          fontSize,
          patchDimensions: { width, height },
          stageDimensions: {
            width: parseFloat(computed.width),
            height: parseFloat(computed.height),
          },
          paintedDimensions,
          dimensionError,
          declared: element.getAttribute('style'),
          matrix: computed.transform,
          parents,
          local,
          native,
          analytical,
          withoutSourceDepth,
          depthContribution: Math.max(
            ...analytical.map((point, index) => distance(point, withoutSourceDepth[index]))
          ),
          projectionError: Math.max(
            ...native.map((point, index) => distance(point, analytical[index]))
          ),
        };
      };
      const headParent = element => element.closest('.lia-body-motion');
      const measureSplit = facets => {
        const corners = facets.flatMap((facet, facetIndex) =>
          facet.local.slice(0, 4).flatMap((point, corner) =>
            Math.abs(point.z) < 1e-5
              ? [
                  {
                    facetIndex,
                    sourceIndex: facet.sourceIndex,
                    corner,
                    front: facet.front,
                    local: point,
                    native: facet.native[corner],
                    analytical: facet.analytical[corner],
                  },
                ]
              : []
          )
        );
        const pairs = corners
          .filter(point => point.front)
          .map(front => {
            const matches = corners.filter(
              back =>
                !back.front &&
                Math.hypot(
                  back.local.x - front.local.x,
                  back.local.y - front.local.y,
                  back.local.z - front.local.z
                ) < 1e-5
            );
            if (matches.length !== 1)
              throw new Error('Each front split corner needs one source-identical rear corner');
            const back = matches[0];
            return {
              front,
              back,
              gap: distance(front.native, back.native),
              analyticalGap: distance(front.analytical, back.analytical),
            };
          });
        if (pairs.length !== 4)
          throw new Error('The closed garment requires four paired split corners');
        return pairs;
      };
      return roots.map(root => {
        const variant = root.closest('[data-variant]').dataset.variant;
        const head = root.querySelector('.lia-head');
        if (!head || root.dataset.volumeReady !== 'false')
          throw new Error('A real context-loss fallback is required');
        const fontSize = parseFloat(getComputedStyle(head).fontSize);
        if (!Number.isFinite(fontSize) || fontSize <= 0)
          throw new Error('A finite native em size is required');
        const profile = volumeProfile(style, variant);
        const sourceFacets = scarfWrapFacets(profile.collar);
        const ordered = sourceFacets
          .map((source, sourceIndex) => ({
            source,
            sourceIndex,
            front: source.origin.z + source.horizontal.z / 2 > 0,
          }))
          .sort((a, b) => Number(a.front) - Number(b.front));
        const elements = [...root.querySelectorAll('.lia-scarf-wrap-facet')];
        if (sourceFacets.length !== 32 || elements.length !== 32)
          throw new Error('All 32 original and native facets are required');
        const frame = frameOf(head);
        const facetProjection = elements.map((element, index) => {
          const { source, sourceIndex, front } = ordered[index];
          const actualFront = !!element.closest('.lia-scarf-wrap-layer--front');
          if (actualFront !== front)
            throw new Error(
              'Native DOM facet order differs from the original back/front source order'
            );
          return measureFacet(element, source, sourceIndex, front, fontSize, frame);
        });
        const splitContinuity = measureSplit(facetProjection);
        const knot = root.querySelector('.lia-scarf-wrap-knot');
        const tail = root.querySelector('.lia-scarf-wrap-tail');
        if (!knot || !tail) throw new Error('Both native knot and tail patches are required');
        const [knotSource, tailSource] = scarfKnotFacets(profile.collar);
        const shear = parseFloat(root.style.getPropertyValue('--rig-scarf-trail'));
        if (!Number.isFinite(shear)) throw new Error('A finite native tail shear is required');
        const knotProjection = measureFacet(knot, knotSource, 'knot', true, fontSize, frame, {
          shear: 0,
        });
        const tailProjection = measureFacet(tail, tailSource, 'tail', true, fontSize, frame, {
          shear,
        });
        const tailSeam = [
          distance(knotProjection.native[3], tailProjection.native[0]),
          distance(knotProjection.native[2], tailProjection.native[1]),
        ];
        const patches = [...facetProjection, knotProjection, tailProjection];
        return {
          variant,
          style,
          geometryUrl,
          scarfUrl,
          sourceFit: profile.collar,
          fontSize,
          anchor: frame.anchor,
          headMatrix: getComputedStyle(head).transform,
          combinedHeadMatrix: [...frame.combined.toFloat64Array()],
          ancestors: frame.ancestors,
          facetProjection,
          splitContinuity,
          knotProjection,
          tailProjection,
          tailSeam,
          shear,
          maxProjectionError: Math.max(...patches.map(facet => facet.projectionError)),
          maxDimensionError: Math.max(...patches.map(facet => facet.dimensionError)),
          maximumDepthContribution: Math.max(
            ...facetProjection.map(facet => facet.depthContribution)
          ),
          passed:
            patches.every(facet => facet.projectionError <= 0.05 && facet.dimensionError <= 0.05) &&
            splitContinuity.every(pair => pair.gap <= 0.05) &&
            tailSeam.every(gap => gap <= 0.05),
        };
      });
    },
    { style, geometryUrl: sourceUrl('volume-geometry'), scarfUrl: sourceUrl('scarf-wrap') }
  );
}
