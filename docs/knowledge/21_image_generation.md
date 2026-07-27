# AI Image Generation

## How do I generate an image?
Simply ask the assistant to create an image. For example: "Generate an image of an astronaut cat" or "Draw me a sunset over the ocean". The image appears as a card below the assistant's response. Three models are available: **gpt-image-1** (default, best quality), **gpt-image-1.5** (faster, cheaper), and **gpt-image-1-mini** (fastest, cheapest). The administrator configures the active model in the LLM settings.

## Can I edit a generated image?
Yes! After generating an image, you can ask the assistant to modify it. For example: "Make it more realistic" or "Add a hat to the cat". The assistant automatically uses the most recent image in the conversation — you don't need to reference it explicitly.

## How do I configure image quality and size?
Go to **Settings > Preferences > AI Image Generation**. You can choose: **Quality** (Low = fastest and cheapest, Medium, High = best quality but slowest and most expensive), **Size** (Square 1024x1024, Portrait 1024x1536, Landscape 1536x1024), and **Format** (PNG or WebP). Higher quality images cost more and take longer to generate (up to 90 seconds for high quality).

## How much does image generation cost?
Cost depends on the model, quality, and size. **gpt-image-1**: Low $0.011–$0.016, Medium $0.042–$0.063, High $0.167–$0.250. **gpt-image-1.5**: Low $0.009–$0.013, Medium $0.034–$0.050, High $0.133–$0.200. **gpt-image-1-mini**: Low $0.005–$0.006, Medium $0.011–$0.015, High $0.036–$0.052. All prices are per image in USD. Image generation costs are tracked and consolidated with text LLM costs in the debug panel and your usage summary.

## Is there a limit to how many images I can generate?
Two safeguards apply. Your account's **usage limits** (cost caps per billing cycle, set by the administrator) cover image generation costs like any other cost. On top of that, a **technical rate limit** protects against runaway loops: by default, 10 image generations (and 10 edits) per 5 minutes per user. Normal use is unaffected; if the limit is reached, the assistant tells you how long to wait before trying again. The administrator can tune both the threshold and the window via the IMAGE_GENERATION_RATE_LIMIT_CALLS and IMAGE_GENERATION_RATE_LIMIT_WINDOW environment variables.

## Is the image generation feature enabled by default?
Yes, image generation is enabled by default for all users. The administrator can disable it globally via the IMAGE_GENERATION_ENABLED environment variable. Individual users can toggle it in Settings > Preferences.

## How do I download a generated image?
Three options: **(1)** Click the download button (arrow icon) that appears on hover over the image in the chat — on mobile, the button is always visible. **(2)** Open the full-screen lightbox by clicking the image, then use the download button in the top-right corner. **(3)** On mobile, long-press the image to trigger the native browser "Save Image" menu, just like on any other website.

## How long does a generated image stay available?

Not forever. A generated image is stored as an attachment with an expiry, and a
scheduled cleanup removes expired attachments every few hours. Each image card
now states the deadline it received from the server, and switches to an amber
tone in the final hours so you can download it in time.

The deadline always comes from the server rather than being written into the
interface: the retention window is configurable by the administrator, so a
duration hard-coded in the app would eventually be wrong. Images generated before
this was introduced simply say nothing rather than guess.

## Are my generated images saved?
Yes, images are saved as attachments on disk and linked to your conversation. They persist across page reloads. When you delete a conversation, all associated images are automatically cleaned up.
