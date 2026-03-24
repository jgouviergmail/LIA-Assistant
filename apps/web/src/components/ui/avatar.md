# Avatar Component Documentation

## Overview

The `Avatar` component is a generic, reusable UI component for displaying profile pictures, user avatars, contact photos, and any circular/rounded image with enhanced visual effects.

**Location**: `src/components/ui/avatar.tsx`

**Created**: 2025-11-13
**Architecture Pattern**: Class Variance Authority (CVA) + Tailwind 4.0 OKLCH

---

## Features

✅ **Multiple Shape Variants**: Circular, rounded, square
✅ **Size Variants**: xs, sm, md, lg, xl, 2xl (24px → 128px)
✅ **Visual Effects**: Glass (glassmorphism), Glow (hover effect), None
✅ **Automatic Fallback**: Initials with color-hashed background if no image
✅ **Lazy Loading**: Built-in skeleton loader during image load
✅ **Status Badge**: Optional badges (online, offline, away, busy, verified)
✅ **Accessibility**: Proper alt text, ARIA labels, keyboard navigation
✅ **Error Handling**: Graceful fallback on image load failure
✅ **Hover Effects**: Scale, shadow, glow (configurable)
✅ **Avatar Groups**: Display multiple avatars with "+N" overflow

---

## Basic Usage

### Simple Avatar with Image

```tsx
import { Avatar } from '@/components/ui/avatar';

<Avatar src="https://example.com/photo.jpg" alt="John Doe" name="John Doe" />;
```

### Fallback to Initials (No Image)

```tsx
<Avatar name="Jane Smith" size="lg" />
// Displays: "JS" on color-hashed background
```

### With Status Badge

```tsx
<Avatar src="https://..." name="Alice" status="online" variant="circular" size="md" />
```

---

## Props API

### `AvatarProps`

| Prop           | Type                                                              | Default      | Description                                                    |
| -------------- | ----------------------------------------------------------------- | ------------ | -------------------------------------------------------------- |
| `src`          | `string`                                                          | `undefined`  | Image source URL                                               |
| `alt`          | `string`                                                          | `undefined`  | Alt text for accessibility (required if src provided)          |
| `name`         | `string`                                                          | `''`         | Display name (used for initials fallback and color generation) |
| `variant`      | `'circular'` \| `'rounded'` \| `'square'`                         | `'circular'` | Shape of the avatar                                            |
| `size`         | `'xs'` \| `'sm'` \| `'md'` \| `'lg'` \| `'xl'` \| `'2xl'`         | `'md'`       | Size variant                                                   |
| `effect`       | `'none'` \| `'glass'` \| `'glow'`                                 | `'glass'`    | Visual effect style                                            |
| `status`       | `'online'` \| `'offline'` \| `'away'` \| `'busy'` \| `'verified'` | `undefined`  | Status badge                                                   |
| `className`    | `string`                                                          | `undefined`  | Additional CSS classes                                         |
| `disableHover` | `boolean`                                                         | `false`      | Disable hover effects                                          |
| `loading`      | `boolean`                                                         | `false`      | Show loading skeleton                                          |
| `onClick`      | `() => void`                                                      | `undefined`  | Click handler (makes avatar clickable)                         |

---

## Size Reference

| Size  | Dimensions    | Font Size | Use Case                         |
| ----- | ------------- | --------- | -------------------------------- |
| `xs`  | 24px × 24px   | 10px      | Tiny icons, inline mentions      |
| `sm`  | 32px × 32px   | 12px      | Compact lists, comments          |
| `md`  | 48px × 48px   | 14px      | **Default**, standard lists      |
| `lg`  | 64px × 64px   | 16px      | Prominent display, cards         |
| `xl`  | 96px × 96px   | 18px      | Profile headers, contact details |
| `2xl` | 128px × 128px | 20px      | Large profile pages              |

---

## Variant Examples

### Circular (Default)

Perfect for profile photos, user avatars.

```tsx
<Avatar src="https://..." name="John Doe" variant="circular" size="lg" effect="glass" />
```

**Visual**: Perfectly round with glassmorphism effect, gradient overlay, border.

### Rounded

Good for app icons, organization logos.

```tsx
<Avatar src="https://..." name="Acme Corp" variant="rounded" size="md" />
```

**Visual**: Rounded corners (`rounded-lg`), softer than square.

### Square

For geometric designs, album art.

```tsx
<Avatar src="https://..." alt="Album Cover" variant="square" size="xl" />
```

---

## Effect Variants

### Glass (Glassmorphism)

- Border: 2px semi-transparent
- Shadow: `shadow-lg` → `shadow-xl` on hover
- Gradient overlay: `from-transparent to-background/10`
- **Use Case**: Professional, modern look (default for profile photos)

```tsx
<Avatar src="..." name="..." effect="glass" />
```

### Glow

- Radial gradient glow on hover
- Scale transform: `scale(1.05)` on hover
- Enhanced shadow: `shadow-2xl`
- **Use Case**: Interactive avatars, clickable elements

```tsx
<Avatar src="..." name="..." effect="glow" onClick={() => openProfile()} />
```

### None

- No special effects, just the image/initials
- **Use Case**: Minimalist design, high-density layouts

```tsx
<Avatar src="..." name="..." effect="none" />
```

---

## Status Badges

Add a status indicator in the bottom-right corner:

```tsx
<Avatar
  src="https://..."
  name="Alice"
  status="online"  // Green dot
/>

<Avatar
  name="Bob"
  status="busy"  // Red dot
/>

<Avatar
  src="https://..."
  name="Charlie"
  status="verified"  // Blue checkmark
/>
```

**Available Statuses**:

- `online`: Green (success color)
- `offline`: Gray (muted color)
- `away`: Orange (warning color)
- `busy`: Red (destructive color)
- `verified`: Blue (primary color) with checkmark icon

---

## Avatar Group

Display multiple avatars in a row with spacing:

```tsx
import { AvatarGroup } from '@/components/ui/avatar';

<AvatarGroup
  avatars={[
    { src: 'https://...', name: 'Alice' },
    { src: 'https://...', name: 'Bob' },
    { name: 'Charlie' },
    { name: 'Diana' },
    { name: 'Eve' },
    { name: 'Frank' },
  ]}
  max={5}
  size="sm"
  spacing="tight"
/>;
```

**Result**: Shows 5 avatars + "+1" badge for the remaining.

### `AvatarGroupProps`

| Prop        | Type                                 | Default      | Description                            |
| ----------- | ------------------------------------ | ------------ | -------------------------------------- |
| `avatars`   | `AvatarProps[]`                      | **required** | Array of avatar configurations         |
| `max`       | `number`                             | `5`          | Maximum avatars to display before "+N" |
| `size`      | AvatarProps['size']                  | `'md'`       | Size of all avatars in group           |
| `spacing`   | `'tight'` \| `'normal'` \| `'loose'` | `'normal'`   | Negative space between avatars         |
| `className` | `string`                             | `undefined`  | Additional CSS classes                 |

---

## Advanced Features

### Color-Hashed Initials

When no `src` is provided, the component generates:

1. **Initials**: First + Last initial (e.g., "John Doe" → "JD")
2. **Background Color**: Deterministic hash from name → HSL hue (0-360°)

**Algorithm**: djb2 hash (consistent color for same name across sessions)

```tsx
// Same name = same color always
<Avatar name="John Doe" /> // Hue: 237° (blue-ish)
<Avatar name="Jane Smith" /> // Hue: 112° (green-ish)
```

**Utility Functions** (exported):

```tsx
import { stringToColor, getInitials } from '@/components/ui/avatar';

const color = stringToColor('Alice'); // "hsl(203, 60%, 50%)"
const initials = getInitials('Bob Jones'); // "BJ"
```

### Lazy Loading

Built-in lazy loading with skeleton placeholder:

```tsx
<Avatar
  src="https://slow-server.com/image.jpg"
  name="Loading User"
  loading={true} // Shows skeleton
/>
```

**Automatic Behavior**:

- Image starts loading when component mounts (`loading="lazy"`)
- Skeleton shows during load (`Skeleton` component)
- Fade-in transition when loaded (`opacity-0` → `opacity-100`)
- Graceful fallback to initials on error

### Clickable Avatars

Make avatars interactive:

```tsx
<Avatar src="https://..." name="Alice" onClick={() => router.push('/profile/alice')} />
```

**Behavior**:

- Cursor changes to pointer
- Active state: `scale(0.95)` on click
- Keyboard accessible (tabIndex=0)
- ARIA role="button"

---

## Integration Examples

### Google Contacts (Current Use Case)

```tsx
// In response_node.py, generate Markdown:
summary += f"![Photo]({photo_url})\n"

// In MarkdownContent.tsx, render with Avatar:
<Avatar
  src="https://lh3.googleusercontent.com/..."
  alt="Photo"
  name={contactName}
  variant="circular"
  size="xl"
  effect="glow"
/>
```

### User Profiles (Future)

```tsx
<Avatar
  src={user.avatarUrl}
  name={user.fullName}
  status={user.isOnline ? 'online' : 'offline'}
  variant="circular"
  size="lg"
  onClick={() => openUserProfile(user.id)}
/>
```

### Chat Messages (Future)

```tsx
<div className="flex items-start gap-3">
  <Avatar src={message.sender.avatar} name={message.sender.name} size="sm" variant="circular" />
  <div className="message-content">{message.text}</div>
</div>
```

### Team Members List (Future)

```tsx
<AvatarGroup
  avatars={team.members.map(m => ({
    src: m.avatar,
    name: m.name,
    status: m.onlineStatus,
  }))}
  max={10}
  size="md"
  spacing="normal"
/>
```

---

## Accessibility

The Avatar component follows WCAG 2.1 AA standards:

✅ **Alt Text**: Required `alt` prop when `src` is provided
✅ **ARIA Labels**: Status badges have `aria-label` and `title`
✅ **Keyboard Navigation**: Clickable avatars have `tabIndex={0}`
✅ **Screen Reader**: Initials fallback readable (text content)
✅ **Contrast**: Initials on hashed background meet 4.5:1 ratio
✅ **Focus Visible**: Ring outline on keyboard focus

```tsx
// Accessible example
<Avatar
  src="https://..."
  alt="Profile photo of John Doe, Software Engineer"
  name="John Doe"
  onClick={openProfile}
/>
```

---

## Performance Considerations

1. **Lazy Loading**: Images use `loading="lazy"` attribute
2. **Memoization**: Initials and color are computed with `React.useMemo`
3. **Skeleton**: Shows immediately, no layout shift
4. **Error Handling**: Fallback to initials on 404/500
5. **CSS-in-JS Avoided**: Pure Tailwind classes (no runtime overhead)

**Bundle Impact**: ~2KB gzipped (including CVA)

---

## Theme Integration

The Avatar component automatically adapts to:

- **Theme Variants**: Professional, Ocean, Forest (via CSS variables)
- **Dark Mode**: `dark:` variants for border, shadow, overlay
- **OKLCH Color Space**: All colors use OKLCH for perceptual uniformity

**Example**: Primary color automatically changes based on active theme.

---

## Future Enhancements (Roadmap)

🔜 **Upload/Edit**: Built-in upload button for changing avatar
🔜 **Cropping**: Integrated image cropper for perfect framing
🔜 **Zoom Modal**: Click to view full-size image in lightbox
🔜 **Animation**: Entrance animations (fade, scale, slide)
🔜 **Badges**: Custom badge content (not just status)
🔜 **Ring Colors**: Customize border color per status

---

## Best Practices

### ✅ DO

- Use `circular` variant for people (profiles, contacts, users)
- Use `rounded` variant for organizations, apps, brands
- Provide meaningful `alt` text for accessibility
- Use `name` prop even when `src` is present (fallback on error)
- Use `xl` or `2xl` size for prominent profile displays
- Use `AvatarGroup` for team/collaborator lists

### ❌ DON'T

- Don't use `square` variant for profile photos (looks harsh)
- Don't omit `alt` text when using `src` (accessibility violation)
- Don't use `xs` size for main profile photos (too small)
- Don't disable hover effects without reason (UX expectation)
- Don't use `effect="glow"` for non-interactive elements (misleading)

---

## Testing

```tsx
// Unit tests
import { render, screen } from '@testing-library/react';
import { Avatar } from '@/components/ui/avatar';

test('renders image when src provided', () => {
  render(<Avatar src="https://test.com/img.jpg" alt="Test" />);
  expect(screen.getByAltText('Test')).toBeInTheDocument();
});

test('renders initials fallback when no src', () => {
  render(<Avatar name="John Doe" />);
  expect(screen.getByText('JD')).toBeInTheDocument();
});

test('shows skeleton during loading', () => {
  render(<Avatar src="..." loading={true} />);
  expect(screen.getByRole('status')).toBeInTheDocument();
});
```

---

## Changelog

**v1.0.0** (2025-11-13):

- Initial release
- CVA-based variants
- Lazy loading with skeleton
- Status badges
- Avatar groups
- Color-hashed initials
- Accessibility compliant
- Tailwind 4.0 OKLCH integration

---

## Support

For questions or issues:

1. Check this documentation
2. Review examples in `/components/chat/MarkdownContent.tsx`
3. Consult Tailwind 4.0 docs for custom styling
4. Open GitHub issue with reproduction case

---

**Maintainer**: Architecture Team
**Last Updated**: 2025-11-13
**License**: Internal Use
