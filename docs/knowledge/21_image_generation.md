# AI Image Generation

## How do I generate an image?
Simply ask the assistant to create an image. For example: "Generate an image of an astronaut cat" or "Draw me a sunset over the ocean". The image appears as a card below the assistant's response. The assistant uses OpenAI's gpt-image-1 model by default.

## Can I edit a generated image?
Yes! After generating an image, you can ask the assistant to modify it. For example: "Make it more realistic" or "Add a hat to the cat". The assistant automatically uses the most recent image in the conversation — you don't need to reference it explicitly.

## How do I configure image quality and size?
Go to **Settings > Preferences > AI Image Generation**. You can choose: **Quality** (Low = fastest and cheapest, Medium, High = best quality but slowest and most expensive), **Size** (Square 1024x1024, Portrait 1024x1536, Landscape 1536x1024), and **Format** (PNG or WebP). Higher quality images cost more and take longer to generate (up to 90 seconds for high quality).

## How much does image generation cost?
Cost depends on the model, quality, and size. For gpt-image-1: Low quality $0.011-$0.016, Medium $0.042-$0.063, High $0.167-$0.250 per image. Image generation costs are tracked and consolidated with text LLM costs in the debug panel and your usage summary.

## Is the image generation feature enabled by default?
Yes, image generation is enabled by default for all users. The administrator can disable it globally via the IMAGE_GENERATION_ENABLED environment variable. Individual users can toggle it in Settings > Preferences.

## Are my generated images saved?
Yes, images are saved as attachments on disk and linked to your conversation. They persist across page reloads. When you delete a conversation, all associated images are automatically cleaned up.
