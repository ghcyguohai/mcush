/* STM32F207xG, 1024kB FLASH, 128kB SRAM */

USER_HEAP_SIZE = 100K;
USER_STACK_SIZE = 1K;
MEMORY
{
    FLASH (rx)   : ORIGIN = 0x08000000, LENGTH = 1024K
    SRAM (rw)    : ORIGIN = 0x20000000, LENGTH = 128K 
    BKPSRAM (rw) : ORIGIN = 0x40024000, LENGTH = 4K 
}

INCLUDE default.ld

SECTIONS
{
    .bkpsram (NOLOAD):
    {
        . = ALIGN(4);
        *(.bkpsram)
        . = ALIGN(4);
    } >BKPSRAM

}
