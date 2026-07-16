/**
 * Card — the domain-accent lookup (the only real branching), variant styling and
 * the composed sub-components.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '../card';

describe('Card', () => {
  it('renders its children and forwards HTML attributes', () => {
    renderWithProviders(<Card data-testid="c">Body</Card>);
    const card = screen.getByTestId('c');
    expect(card).toHaveTextContent('Body');
  });

  it('applies the domain accent border variable for a known domain', () => {
    renderWithProviders(
      <Card data-testid="c" domainAccent="email">
        x
      </Card>
    );
    expect(screen.getByTestId('c').className).toContain('border-l-[var(--lia-email-accent)]');
  });

  it('adds no accent border when no domain is given', () => {
    renderWithProviders(<Card data-testid="c">x</Card>);
    expect(screen.getByTestId('c').className).not.toContain('border-l-[var(--lia-');
  });

  it('maps the status variant to distinct styling', () => {
    const { rerender } = renderWithProviders(
      <Card data-testid="c" status="default">
        x
      </Card>
    );
    const def = screen.getByTestId('c').className;
    rerender(
      <Card data-testid="c" status="warning">
        x
      </Card>
    );
    expect(screen.getByTestId('c').className).not.toBe(def);
  });

  it('composes header, title, description, content and footer', () => {
    renderWithProviders(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Desc</CardDescription>
        </CardHeader>
        <CardContent>Content</CardContent>
        <CardFooter>Footer</CardFooter>
      </Card>
    );
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('Desc')).toBeInTheDocument();
    expect(screen.getByText('Content')).toBeInTheDocument();
    expect(screen.getByText('Footer')).toBeInTheDocument();
  });
});
